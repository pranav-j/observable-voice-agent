"""The core tools, exposed to LiveKit Agents as raw-schema function tools.

Each one uses the schema generated for text mode and runs the same `dispatch`, so voice
and text can't drift apart. Results go back as JSON strings: LiveKit calls `str()` on
tool output, which would turn a dict into a Python repr.

The turn-taking rule from `tools.turns` applies here too. If the model's words in the
current step ask the caller something, the final actions are held back, and the result
says no follow-up reply is needed, so the turn ends and the caller gets to answer.
"""

from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from livekit.agents import RunContext, ToolResult, function_tool
from livekit.agents.llm import ChatChunk, RawFunctionTool

from voice_order.agent.faults import without_modifiers
from voice_order.store.base import OrderStore
from voice_order.tools.base import Result, Session, Tool, dispatch, to_json
from voice_order.tools.catalog import TOOLS
from voice_order.tools.turns import WAIT_FOR_ANSWER, WAITING_FOR_CALLER, asks_caller

ToolListener = Callable[[str, Result], Awaitable[None]]
# An async tool function: the second type argument is what calling it returns.
LiveKitTool = RawFunctionTool[..., Coroutine[Any, Any, ToolResult]]


class StepText:
    """What the model has said so far in the current LLM step."""

    def __init__(self) -> None:
        self.text = ""

    def reset(self) -> None:
        self.text = ""

    def add(self, chunk: object) -> None:
        if isinstance(chunk, str):
            self.text += chunk
        elif isinstance(chunk, ChatChunk) and chunk.delta and chunk.delta.content:
            self.text += chunk.delta.content

    @property
    def asked_caller(self) -> bool:
        return asks_caller(self.text)


async def _ignore(name: str, result: Result) -> None:
    return None


def make_tool(
    tool: Tool[Any],
    session: Session,
    store: OrderStore,
    tools: dict[str, Tool[Any]],
    on_result: ToolListener,
    step: StepText | None = None,
    drop_modifiers: bool = False,
) -> LiveKitTool:
    async def call(
        raw_arguments: dict[str, object], context: RunContext[Any] | None = None
    ) -> ToolResult:
        if drop_modifiers:  # FAULT=drop_modifiers
            raw_arguments = without_modifiers(raw_arguments)
        asked = step is not None and step.asked_caller
        before = session.order
        if asked and tool.name in WAIT_FOR_ANSWER:
            result = WAITING_FOR_CALLER
        else:
            result = dispatch(session, tools, tool.name, raw_arguments)
        if session.order is not before:
            await store.save(session.order)
        await on_result(tool.name, result)
        # After a question, no follow-up step: the caller speaks next.
        return ToolResult(to_json(result), reply_required=not asked)

    raw_schema = {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters_schema(),
    }
    made: LiveKitTool = function_tool(call, raw_schema=raw_schema)
    return made


def livekit_tools(
    session: Session,
    store: OrderStore,
    on_result: ToolListener = _ignore,
    step: StepText | None = None,
    tools: dict[str, Tool[Any]] = TOOLS,
    drop_modifiers: bool = False,
) -> list[LiveKitTool]:
    """One LiveKit tool per core tool, all acting on the same call session."""
    return [
        make_tool(t, session, store, tools, on_result, step, drop_modifiers) for t in tools.values()
    ]
