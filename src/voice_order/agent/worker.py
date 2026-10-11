"""LiveKit Agents worker. Voice wiring only: all order logic lives in the core.

Run with `python -m livekit.agents start src/voice_order/agent/worker.py --dev`
(or `make dev`). See docs/adr/0004-voice-pipeline.md for the choices made here.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    ConversationItemAddedEvent,
    JobContext,
    JobProcess,
    ModelSettings,
    UserStateChangedEvent,
    inference,
    llm,
)
from livekit.plugins import openai as lk_openai
from livekit.plugins import silero
from openai.types import Reasoning

from voice_order.agent.faults import SLOW_LLM_DELAY_S, delay_first
from voice_order.agent.filler import fillers, with_filler
from voice_order.agent.tools import StepText, livekit_tools
from voice_order.config import Settings, get_settings
from voice_order.menu.loader import load_menu
from voice_order.order.state import abandon
from voice_order.prompts.loader import AGENT_SYSTEM_VERSION, agent_system_prompt, greeting_prompt
from voice_order.recording.session import save_session
from voice_order.store.postgres import PostgresOrderStore
from voice_order.telemetry.tracing import setup_tracing
from voice_order.telemetry.turns import TurnLog
from voice_order.telemetry.usage import load_rates
from voice_order.tools.base import CallEnd, Result, Session
from voice_order.tools.catalog import order_view
from voice_order.tools.turns import MAX_TOOL_ROUNDS

log = logging.getLogger("voice_order.worker")

ORDER_TOPIC = "order"  # the web UI's order panel listens on this data topic
TURN_TOPIC = "turn"  # per-turn timings, the same records written to turns.jsonl
TIME_UP = "Sorry, we're out of time for this call. Please call back to finish your order."
AWAY = "I haven't heard from you in a while, so I'll end the call. Please call back anytime."


class OrderAgent(Agent):
    """Records the text of each LLM step, so the tools can tell when it asked the caller."""

    def __init__(
        self,
        *,
        step: StepText,
        first_token_delay: float = 0.0,
        filler_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.step = step
        self.first_token_delay = first_token_delay  # only set by FAULT=slow_llm
        self.filler_after = filler_after  # None: no filler phrases
        self.next_filler = fillers()
        self.filler_due = False

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        self.filler_due = True  # only the first LLM step of a turn may get a filler

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ) -> AsyncIterable[Any]:
        self.step.reset()
        chunks = delay_first(
            Agent.default.llm_node(self, chat_ctx, tools, model_settings), self.first_token_delay
        )
        filler_due, self.filler_due = self.filler_due, False
        if filler_due and self.filler_after is not None:
            chunks = with_filler(
                chunks,
                after=self.filler_after,
                filler=self.next_filler(),
                starts_tool_call=_is_tool_call,
            )
        async for chunk in chunks:
            self.step.add(chunk)
            yield chunk


def _is_tool_call(chunk: object) -> bool:
    return isinstance(chunk, llm.ChatChunk) and bool(chunk.delta and chunk.delta.tool_calls)


def prewarm(proc: JobProcess) -> None:
    # Loading the VAD model blocks, so do it once per process, before calls arrive.
    proc.userdata["vad"] = silero.VAD.load()


def build_session(settings: Settings, vad: Any) -> AgentSession[None]:
    key = settings.openai_api_key.get_secret_value()
    return AgentSession(
        stt=lk_openai.STT(model=settings.stt_model, api_key=key),
        llm=lk_openai.responses.LLM(
            model=settings.llm_model,
            api_key=key,
            reasoning=Reasoning(effort="none"),
            # Resend the whole conversation each step instead of chaining on the last
            # response. When chaining, the plugin resends tool calls the server already
            # has, so each call shows up twice with one output, and the model sometimes
            # repeats the call it thinks is unanswered (an item added three times).
            store=False,
        ),
        tts=lk_openai.TTS(
            model=settings.tts_model,
            voice=settings.tts_voice,
            api_key=key,
            response_format=settings.tts_format,
        ),
        vad=vad,
        turn_handling={
            # Local models only: the defaults in dev mode would call LiveKit's cloud.
            # FAULT=aggressive_eou drops the semantic detector as well: with it, a 150 ms
            # wait changed nothing, since the model holds the turn on an unfinished sentence.
            "turn_detection": "vad"
            if settings.fault == "aggressive_eou"
            else inference.TurnDetector(version="v1-mini"),
            "endpointing": {"min_delay": settings.effective_eou_silence_ms / 1000},
            "interruption": {"enabled": settings.fault != "no_barge_in", "mode": "vad"},
            "preemptive_generation": {"enabled": settings.enable_preemptive_generation},
        },
        user_away_timeout=settings.idle_timeout_seconds,
        max_tool_steps=MAX_TOOL_ROUNDS,  # LiveKit's default is 3; text mode allows the same
    )


async def publish(room: rtc.Room, topic: str, payload: dict[str, Any]) -> None:
    try:
        await room.local_participant.publish_data(json.dumps(payload), topic=topic, reliable=True)
    except Exception:  # the UI missing an update must never break the call
        log.warning("could not publish %s update", topic, exc_info=True)


settings = get_settings()
server = AgentServer(
    setup_fnc=prewarm,
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret.get_secret_value(),
)


async def on_session_end(ctx: JobContext) -> None:
    # Runs after the session closes and before LiveKit deletes the job's temp directory,
    # which is where the audio recording lives.
    try:
        folder = Path(settings.recordings_dir) / ctx.job.room.name
        folder.mkdir(parents=True, exist_ok=True)
        config = settings.voice_config() | {"agent_prompt_version": AGENT_SYSTEM_VERSION}
        (folder / "config.json").write_text(json.dumps(config, indent=2))
        out = save_session(ctx.make_session_report(), folder, load_rates())
        log.info("saved recording to %s", out)
    except Exception:
        log.exception("could not save the session recording")


@server.rtc_session(agent_name=settings.agent_name, on_session_end=on_session_end)
async def entrypoint(ctx: JobContext) -> None:
    menu = load_menu()
    call = Session.start(menu, ctx.job.room.name)  # the room name is the session id
    session_id = call.order.session_id
    tracing = setup_tracing(
        settings.phoenix_collector_endpoint,
        {
            "session_id": session_id,
            "stt.provider": "openai",
            "stt.model": settings.stt_model,
            "llm.provider": "openai",
            "llm.model": settings.llm_model,
            "tts.provider": "openai",
            "tts.model": settings.tts_model,
        },
    )

    async def flush_traces() -> None:
        tracing.force_flush()

    ctx.add_shutdown_callback(flush_traces)
    turns = TurnLog(Path(settings.recordings_dir) / session_id / "turns.jsonl")
    store = await PostgresOrderStore.connect(settings.database_url)

    async def close_store() -> None:
        # The caller may hang up mid-order: close the order and save its final state.
        if call.ending is None:
            call.order = abandon(call.order)
            await store.save(call.order)
        await store.close()

    ctx.add_shutdown_callback(close_store)
    await store.save(call.order)

    async def on_tool_result(name: str, result: Result) -> None:
        await publish(
            ctx.room, ORDER_TOPIC, {"session_id": call.order.session_id, **order_view(call)}
        )

    if settings.fault != "none":
        log.warning("FAULT=%s: this worker is broken on purpose", settings.fault)
    step = StepText()
    agent = OrderAgent(
        step=step,
        first_token_delay=SLOW_LLM_DELAY_S if settings.fault == "slow_llm" else 0.0,
        filler_after=settings.filler_after_ms / 1000 if settings.enable_filler_phrases else None,
        instructions=agent_system_prompt(menu.restaurant).text,
        tools=livekit_tools(
            call, store, on_tool_result, step, drop_modifiers=settings.fault == "drop_modifiers"
        ),
    )
    session = build_session(settings, ctx.proc.userdata["vad"])
    background: set[asyncio.Task[None]] = set()

    @session.on("conversation_item_added")
    def _on_item(ev: ConversationItemAddedEvent) -> None:
        if ev.item.type == "message":
            record = turns.add(ev.item)
            # The UI's latency overlay uses exactly these numbers, so it matches the traces.
            task = asyncio.create_task(publish(ctx.room, TURN_TOPIC, record))
            background.add(task)
            task.add_done_callback(background.discard)
            if ev.item.role == "user":
                call.caller_spoke()  # lets confirm_order check the caller replied to the read-back
            elif ev.item.role == "assistant":
                # An interrupted message holds only what was played, so a read-back the
                # caller cut off doesn't count as heard. The flag alone isn't enough: it can
                # be set after playout ended, when a held-back tool call kept the speech open.
                call.agent_said(ev.item.text_content or "", interrupted=ev.item.interrupted)

    @session.on("agent_state_changed")
    def _on_agent_state(ev: AgentStateChangedEvent) -> None:
        # end_call or transfer_to_human ran and the goodbye has been spoken: hang up.
        if call.ending is not None and ev.new_state == "listening":
            ctx.shutdown(reason=f"{call.ending.kind}: {call.ending.reason}")

    async def end_with(line: str, reason: str) -> None:
        if call.ending is None:
            call.order = abandon(call.order)
            call.ending = CallEnd(kind="end_call", reason=reason)
            await store.save(call.order)
            await session.say(line, allow_interruptions=False)

    @session.on("user_state_changed")
    def _on_user_state(ev: UserStateChangedEvent) -> None:
        if ev.new_state == "away":
            # The loop only holds weak references to tasks; keep one until it's done.
            task = asyncio.create_task(end_with(AWAY, "caller went quiet"))
            background.add(task)
            task.add_done_callback(background.discard)

    await session.start(agent, room=ctx.room, record=True)  # stereo: caller left, agent right
    await publish(ctx.room, ORDER_TOPIC, {"session_id": call.order.session_id, **order_view(call)})
    await session.say(greeting_prompt(menu.restaurant).text)

    async def time_limit() -> None:
        await asyncio.sleep(settings.max_call_seconds)
        await end_with(TIME_UP, "max call length reached")

    timer = asyncio.create_task(time_limit())
    ctx.add_shutdown_callback(lambda: _cancel(timer))


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
