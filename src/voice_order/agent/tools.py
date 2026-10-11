"""The core tools, exposed to LiveKit Agents as raw-schema function tools.

Each one uses the schema generated for text mode and runs the same `dispatch`, so voice
and text can't drift apart. Results go back as JSON strings: LiveKit calls `str()` on
tool output, which would turn a dict into a Python repr.
"""

from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import RawFunctionTool

from voice_order.store.base import OrderStore
from voice_order.tools.base import Result, Session, Tool, dispatch, to_json
from voice_order.tools.catalog import TOOLS

ToolListener = Callable[[str, Result], Awaitable[None]]
# An async tool function: the second type argument is what calling it returns.
LiveKitTool = RawFunctionTool[..., Coroutine[Any, Any, str]]


async def _ignore(name: str, result: Result) -> None:
    return None


def make_tool(
    tool: Tool[Any],
    session: Session,
    store: OrderStore,
    tools: dict[str, Tool[Any]],
    on_result: ToolListener,
) -> LiveKitTool:
    async def call(raw_arguments: dict[str, object], context: RunContext[Any] | None = None) -> str:
        before = session.order
        result = dispatch(session, tools, tool.name, raw_arguments)
        if session.order is not before:
            await store.save(session.order)
        await on_result(tool.name, result)
        return to_json(result)

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
    tools: dict[str, Tool[Any]] = TOOLS,
) -> list[LiveKitTool]:
    """One LiveKit tool per core tool, all acting on the same call session."""
    return [make_tool(t, session, store, tools, on_result) for t in tools.values()]
