"""Play one scenario over real audio: the simulated caller joins the room and talks.

The LLM caller (TextCaller) decides what to say; the AudioCaller says it, with the
persona's voice, noise and scripted pauses, and listens to the agent. Interruptions are
timed against the agent's actual speech. Afterwards the order is scored from the store,
timing metrics come from the received audio, and the agent's cost from the usage file
the worker saved for the call.
"""

import asyncio
import json
import secrets
import time
import wave
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from evals.audio.caller import VOICE_POOL, AudioCaller, Hearing
from evals.audio.detector import DETECTOR_SETTINGS
from evals.audio.detector import SAMPLE_RATE as LISTEN_RATE
from evals.audio.metrics import audio_metrics, doubled_replies
from evals.caller.text_caller import CALLER_PROMPT_VERSION, Phase, TextCaller
from evals.scenario import Behavior, Scenario
from evals.scoring.order import score_order
from evals.text_run import EndReason, RunResult, TranscriptEntry
from voice_order.api.app import join_token
from voice_order.config import Settings
from voice_order.menu.models import Menu
from voice_order.order.state import spoken_digits
from voice_order.prompts.loader import AGENT_SYSTEM_VERSION
from voice_order.store.base import OrderStore
from voice_order.textmode.llm import LLMClient, Usage

GREETING_WAIT_S = 30.0
REPLY_WAIT_S = 30.0
USAGE_WAIT_S = 60.0  # saving the recording can take a while after the caller leaves


def _pauses(scenario: Scenario) -> dict[int, int]:
    return {
        b.trigger.turn: b.pause_ms or 0
        for b in scenario.behaviors
        if b.action == "pause_mid_utterance" and b.trigger.turn is not None
    }


def _phone_pause(scenario: Scenario) -> int:
    """The pause for the utterance that gives the phone number, whichever turn that is."""
    return next(
        (
            b.pause_ms or 0
            for b in scenario.behaviors
            if b.action == "pause_mid_utterance" and b.trigger.phase == "phone"
        ),
        0,
    )


def gives_phone_number(text: str) -> bool:
    return len(spoken_digits(text)) >= 10


async def _read_usage(folder: Path) -> dict[str, Any] | None:
    """The worker writes usage.json when the call ends; give it a moment."""
    deadline = time.monotonic() + USAGE_WAIT_S
    while time.monotonic() < deadline:
        path = folder / "usage.json"
        if path.exists():
            return dict(json.loads(path.read_text()))
        await asyncio.sleep(0.5)
    return None


def _save_raw(out: Path, caller: AudioCaller, transcript: list[TranscriptEntry]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    audio, start = caller.agent_audio()
    with wave.open(str(out / "agent_received.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(LISTEN_RATE)
        w.writeframes(audio.tobytes())
    timeline = {
        "agent_audio_start": start,
        "detector": DETECTOR_SETTINGS,
        "caller": [u.__dict__ | {"pauses": list(u.pauses)} for u in caller.utterances],
        "heard_caller": caller.heard_caller,
        "agent_transcripts": caller.agent.transcripts,
    }
    (out / "timeline.json").write_text(json.dumps(timeline, indent=2))
    (out / "transcript.json").write_text(json.dumps([e.model_dump() for e in transcript], indent=2))


async def run_audio_scenario(
    scenario: Scenario,
    run: int,
    *,
    settings: Settings,
    menu: Menu,
    store: OrderStore,
    caller_llm: LLMClient,
    client: AsyncOpenAI,
    hearing: Hearing = "transcript",
    raw_dir: Path | None = None,
) -> RunResult:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    session_id = f"audio-{scenario.id}-r{run}-{stamp}-{secrets.token_hex(2)}"
    identity = f"caller-{secrets.token_hex(3)}"
    persona = scenario.persona
    noise = (persona.noise.clip, persona.noise.snr_db) if persona.noise else None
    caller = AudioCaller(
        client=client, voice=persona.voice or "", style=persona.style, noise=noise, hearing=hearing
    )
    brain = TextCaller(caller_llm, scenario, menu.restaurant)
    transcript: list[TranscriptEntry] = []
    pauses = _pauses(scenario)
    phone_pause = _phone_pause(scenario)
    interrupts = [b for b in scenario.behaviors if b.action == "interrupt"]
    fired: set[int] = set()
    end_reason: EndReason = "max_turns"
    error: str | None = None
    turns = 0
    started = time.monotonic()

    def armed(since: float, onset: float) -> Behavior | None:
        """An interruption whose trigger matches the agent speech that just started."""
        for i, b in enumerate(interrupts):
            if i in fired:
                continue
            rb = caller.agent.readback_started
            if (
                (b.trigger.phase == "readback" and rb is not None and rb > since)
                or b.trigger.phase == "any_agent_speech"
                or (b.trigger.turn is not None and brain.turn + 1 == b.trigger.turn)
            ):
                fired.add(i)
                return b
        return None

    async def agent_turn(since: float) -> str:
        """Wait for the agent's reply, interrupting it if a scripted interruption is due."""
        onset = await caller.agent_speaking_after(since, REPLY_WAIT_S)
        if onset is None:
            return ""
        behavior = armed(since, onset)
        if behavior is None or behavior.say is None:
            return await caller.agent_reply(since, REPLY_WAIT_S)
        await asyncio.sleep((behavior.after_ms or 0) / 1000)
        partial = caller.agent.heard_since(since)
        phase: Phase = "readback" if behavior.trigger.phase == "readback" else None
        scripted = await brain.respond(partial or "(the agent is speaking)", phase)
        transcript.append(TranscriptEntry(speaker="agent", text=partial))
        transcript.append(TranscriptEntry(speaker="caller", text=scripted.text, scripted=True))
        utterance = await caller.say(scripted.text, interrupt=True)
        return await caller.agent_reply(utterance.end, REPLY_WAIT_S)

    try:
        await caller.join(
            settings.livekit_url, join_token(settings, session_id, identity), identity
        )
        agent_text = await caller.agent_reply(0.0, GREETING_WAIT_S)
        if not agent_text and caller.agent.last_loud == 0:
            raise RuntimeError("the agent never answered; is the worker running (make worker)?")
        transcript.append(TranscriptEntry(speaker="agent", text=agent_text))
        last_end = caller.now()
        while turns < scenario.max_turns and time.monotonic() - started < settings.max_call_seconds:
            rb = caller.agent.readback_started
            phase: Phase = "readback" if rb is not None and rb > last_end else None
            said = await brain.respond(agent_text, phase)
            if said.text:
                transcript.append(
                    TranscriptEntry(speaker="caller", text=said.text, scripted=said.scripted)
                )
            if said.gave_up:
                end_reason = "caller_gave_up"
                break
            if said.ended or not said.text:
                if said.text and caller.agent.order_status == "draft" and not caller.agent.left:
                    spoken = await caller.say(said.text)  # last words still reach the agent
                    await caller.agent_reply(spoken.end, REPLY_WAIT_S)
                end_reason = (
                    "caller_hung_up_early"
                    if caller.agent.order_status == "draft"
                    else "caller_ended"
                )
                break
            turns += 1
            pause = pauses.get(turns, 0)
            if not pause and phone_pause and gives_phone_number(said.text):
                pause, phone_pause = phone_pause, 0  # only the first time
            spoken = await caller.say(said.text, pause_ms=pause)
            last_end = spoken.end
            agent_text = await agent_turn(spoken.end)
            transcript.append(TranscriptEntry(speaker="agent", text=agent_text))
            if caller.agent.left:
                end_reason = (
                    "transferred" if caller.agent.order_status == "escalated" else "agent_ended"
                )
                break
        if end_reason == "max_turns" and time.monotonic() - started >= settings.max_call_seconds:
            end_reason = "time_limit"
    except Exception as exc:  # one failed call must not stop the suite
        end_reason = "error"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        await caller.leave()
    if caller.send_glitches and error is None:
        # The harness failed, not the agent: don't let it count as the agent's failure.
        end_reason = "error"
        error = f"caller audio went out faster than real time: {caller.send_glitches[0]!r}"

    folder = Path(settings.recordings_dir) / session_id
    usage = await _read_usage(folder)
    config_file = folder / "config.json"  # written by the worker just before usage.json
    agent_config = json.loads(config_file.read_text()) if config_file.exists() else None
    said_file = folder / "transcript.json"
    agent_said = (
        [r["text"] for r in json.loads(said_file.read_text()) if r["role"] == "assistant"]
        if said_file.exists()
        else []
    )
    final = await store.get(session_id)
    timeline = caller.timeline()
    if raw_dir is not None:
        _save_raw(raw_dir / session_id, caller, transcript)
    metrics = audio_metrics(timeline)
    duration = time.monotonic() - started
    return RunResult(
        scenario_id=scenario.id,
        tags=scenario.tags,
        run=run,
        session_id=session_id,
        mode="audio",
        end_reason=end_reason,
        error=error,
        turns=turns,
        duration_s=round(duration, 3),
        score=score_order(final, scenario.expect),
        agent_usage=_agent_usage(usage),
        caller_usage=brain.usage,
        tool_limit_hits=0,
        skipped_behaviors=[],
        agent_model=settings.llm_model,
        caller_model=caller_llm.model,
        agent_prompt_version=AGENT_SYSTEM_VERSION,
        caller_prompt_version=CALLER_PROMPT_VERSION,
        transcript=transcript,
        audio=metrics
        | {
            "hearing": hearing,
            "voice": VOICE_POOL.get(persona.voice or "", "alloy"),
            "noise": {"clip": noise[0], "snr_db": noise[1]} if noise else None,
            "agent_cost_usd": usage.get("total_cost_usd") if usage else None,
            "agent_cost_is_estimate": bool(
                usage and any(m.get("estimated_from_call_length") for m in usage.get("models", []))
            ),
            "call_seconds": usage.get("duration_seconds") if usage else round(duration, 1),
            "agent_config": agent_config,
            "doubled_replies": doubled_replies(agent_said),
            "detector": DETECTOR_SETTINGS,
        },
    )


def _agent_usage(usage: dict[str, Any] | None) -> Usage:
    if not usage:
        return Usage()
    llm = [m for m in usage.get("models", []) if m.get("kind") == "llm"]
    return Usage(
        sum(m.get("input_tokens", 0) for m in llm),
        sum(m.get("output_tokens", 0) for m in llm),
    )
