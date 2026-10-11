"""The agent loop: LLM, tools, repeat until the model answers in words."""

import time
from dataclasses import dataclass
from typing import Any

from voice_order.store.base import OrderStore
from voice_order.textmode.llm import (
    AssistantMessage,
    LLMClient,
    Message,
    ToolCall,
    ToolOutput,
    ToolSpec,
    Usage,
    UserMessage,
)
from voice_order.tools.base import CallEnd, Result, Session, Tool, dispatch, to_json
from voice_order.tools.catalog import TOOLS

MAX_TOOL_ROUNDS = 8
FALLBACK = "Sorry, I didn't catch that. Could you say it again?"


@dataclass(frozen=True)
class ToolEvent:
    name: str
    arguments: str
    result: Result
    duration_ms: float


@dataclass(frozen=True)
class Turn:
    text: str
    tool_events: tuple[ToolEvent, ...]
    usage: Usage
    ending: CallEnd | None
    hit_tool_limit: bool = False


class CallEndedError(RuntimeError):
    pass


class TextAgent:
    def __init__(
        self,
        *,
        llm: LLMClient,
        session: Session,
        store: OrderStore,
        instructions: str,
        tools: dict[str, Tool[Any]] = TOOLS,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ) -> None:
        self.llm = llm
        self.session = session
        self.store = store
        self.instructions = instructions
        self.tools = tools
        self.tool_specs = [ToolSpec.from_tool(t) for t in tools.values()]
        self.max_tool_rounds = max_tool_rounds
        self.history: list[Message] = []
        self.usage = Usage()

    async def start(self, greeting: str) -> str:
        """Save the empty order so the session is findable, then open with a fixed greeting."""
        await self.store.save(self.session.order)
        self.history.append(AssistantMessage(greeting))
        return greeting

    async def respond(self, user_text: str) -> Turn:
        if self.session.ending is not None:
            raise CallEndedError(f"call ended: {self.session.ending.kind}")
        self.history.append(UserMessage(user_text))
        spoken: list[str] = []
        events: list[ToolEvent] = []
        usage = Usage()
        hit_limit = True
        for _ in range(self.max_tool_rounds):
            reply = await self.llm.complete(self.instructions, self.history, self.tool_specs)
            usage += reply.usage
            if reply.text:
                spoken.append(reply.text)
                self.history.append(AssistantMessage(reply.text))
            if not reply.tool_calls:
                hit_limit = False
                break
            for call in reply.tool_calls:
                self.history.append(call)
                event = await self._run(call)
                events.append(event)
                self.history.append(ToolOutput(call.call_id, to_json(event.result)))
        if hit_limit:
            # The model kept calling tools without answering. Stop it and ask again.
            spoken.append(FALLBACK)
            self.history.append(AssistantMessage(FALLBACK))
        self.usage += usage
        return Turn(" ".join(spoken), tuple(events), usage, self.session.ending, hit_limit)

    async def _run(self, call: ToolCall) -> ToolEvent:
        before = self.session.order
        started = time.perf_counter()
        result = dispatch(self.session, self.tools, call.name, call.arguments)
        duration_ms = (time.perf_counter() - started) * 1000
        if self.session.order is not before:
            await self.store.save(self.session.order)
        return ToolEvent(call.name, call.arguments, result, duration_ms)
