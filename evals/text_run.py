"""Play one scenario in text mode: the agent against the simulated caller, then score it."""

import json
import secrets
import time
from typing import Any, Literal

from pydantic import BaseModel

from evals.caller.text_caller import CALLER_PROMPT_VERSION, Phase, TextCaller
from evals.scenario import Scenario
from evals.scoring.order import OrderScore, score_order
from voice_order.menu.models import Menu
from voice_order.prompts.loader import AGENT_SYSTEM_VERSION, agent_system_prompt, greeting_prompt
from voice_order.store.base import OrderStore
from voice_order.textmode.agent import TextAgent, ToolEvent, Turn
from voice_order.textmode.llm import LLMClient, Usage
from voice_order.tools.base import Session

EndReason = Literal[
    "caller_ended",
    "caller_hung_up_early",
    "agent_ended",
    "transferred",
    "caller_gave_up",
    "max_turns",
    "error",
]


class TranscriptEntry(BaseModel):
    speaker: Literal["agent", "caller"]
    text: str
    tool_calls: list[dict[str, Any]] = []
    scripted: bool = False


class RunResult(BaseModel):
    scenario_id: str
    tags: list[str] = []
    run: int
    session_id: str
    mode: Literal["text"] = "text"
    end_reason: EndReason
    error: str | None = None
    turns: int
    duration_s: float
    score: OrderScore
    agent_usage: Usage
    caller_usage: Usage  # tracked separately: not part of the agent's cost
    tool_limit_hits: int
    # Turns where the agent called confirm_order after get_readback without the caller
    # getting a chance to reply. Defaults to 0 so older results files still load.
    confirmed_before_reply: int = 0
    skipped_behaviors: list[str]
    agent_model: str
    caller_model: str
    agent_prompt_version: str
    caller_prompt_version: str
    transcript: list[TranscriptEntry] = []  # left out of results.jsonl; kept in raw/


def _tool_record(event: ToolEvent) -> dict[str, Any]:
    try:
        arguments: Any = json.loads(event.arguments or "{}")
    except json.JSONDecodeError:
        arguments = event.arguments
    record = {"name": event.name, "arguments": arguments, "ok": bool(event.result.get("ok"))}
    if not record["ok"]:
        record["error"] = event.result.get("error")
    return record


def _confirmed_before_reply(events: tuple[ToolEvent, ...]) -> bool:
    """A confirm attempt after a read-back in the same agent turn, i.e. before any reply."""
    readback = False
    for e in events:
        if e.name == "get_readback" and e.result.get("ok"):
            readback = True
        elif e.name == "confirm_order" and readback:
            return True
    return False


def _readback_given(events: tuple[ToolEvent, ...]) -> bool:
    return any(e.name == "get_readback" and e.result.get("ok") for e in events)


async def run_text_scenario(
    scenario: Scenario,
    run: int,
    *,
    menu: Menu,
    store: OrderStore,
    agent_llm: LLMClient,
    caller_llm: LLMClient,
) -> RunResult:
    session_id = f"eval-{scenario.id}-r{run}-{secrets.token_hex(3)}"
    agent = TextAgent(
        llm=agent_llm,
        session=Session.start(menu, session_id),
        store=store,
        instructions=agent_system_prompt(menu.restaurant).text,
    )
    caller = TextCaller(caller_llm, scenario, menu.restaurant)
    transcript: list[TranscriptEntry] = []
    turns = 0
    tool_limit_hits = 0
    confirmed_before_reply = 0
    end_reason: EndReason = "max_turns"
    error: str | None = None
    started = time.perf_counter()

    async def agent_reply(text: str) -> Turn:
        nonlocal turns, tool_limit_hits, confirmed_before_reply
        turn = await agent.respond(text)
        turns += 1
        tool_limit_hits += turn.hit_tool_limit
        confirmed_before_reply += _confirmed_before_reply(turn.tool_events)
        transcript.append(
            TranscriptEntry(
                speaker="agent",
                text=turn.text,
                tool_calls=[_tool_record(e) for e in turn.tool_events],
            )
        )
        return turn

    def order_is_open() -> bool:
        return agent.session.order.status == "draft" and agent.session.ending is None

    try:
        agent_text = await agent.start(greeting_prompt(menu.restaurant).text)
        transcript.append(TranscriptEntry(speaker="agent", text=agent_text))
        phase: Phase = None
        while turns < scenario.max_turns:
            said = await caller.respond(agent_text, phase)
            if said.text:
                transcript.append(
                    TranscriptEntry(speaker="caller", text=said.text, scripted=said.scripted)
                )
            if said.gave_up:
                end_reason = "caller_gave_up"
                break
            if said.ended or not said.text:
                last_turn = None
                if said.text and order_is_open():
                    # "Yes, that's right. Goodbye." can still confirm the order, so the
                    # caller's last words reach the agent before the call ends.
                    last_turn = await agent_reply(said.text)
                if (
                    last_turn is not None
                    and last_turn.ending is not None
                    and last_turn.ending.kind == "transfer"
                ):
                    end_reason = "transferred"
                elif order_is_open():
                    # The caller left mid-order and the agent never ended the call. Labelled
                    # on its own so the report doesn't quietly blame the agent for it.
                    end_reason = "caller_hung_up_early"
                else:
                    end_reason = "caller_ended"
                break

            turn = await agent_reply(said.text)
            agent_text = turn.text
            phase = "readback" if _readback_given(turn.tool_events) else None
            if turn.ending is not None:
                end_reason = "transferred" if turn.ending.kind == "transfer" else "agent_ended"
                break
    except Exception as exc:  # one failed run (e.g. an API error) must not stop the suite
        end_reason = "error"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        # Every run ends with a final, saved status, even after an error.
        await agent.hang_up(f"eval ended: {end_reason}")

    final = await store.get(session_id)  # scored from the store, like the real harness
    return RunResult(
        scenario_id=scenario.id,
        tags=scenario.tags,
        run=run,
        session_id=session_id,
        end_reason=end_reason,
        error=error,
        turns=turns,
        duration_s=round(time.perf_counter() - started, 3),
        score=score_order(final, scenario.expect),
        agent_usage=agent.usage,
        caller_usage=caller.usage,
        tool_limit_hits=tool_limit_hits,
        confirmed_before_reply=confirmed_before_reply,
        skipped_behaviors=[b.action for b in caller.skipped_behaviors],
        agent_model=agent_llm.model,
        caller_model=caller_llm.model,
        agent_prompt_version=AGENT_SYSTEM_VERSION,
        caller_prompt_version=CALLER_PROMPT_VERSION,
        transcript=transcript,
    )
