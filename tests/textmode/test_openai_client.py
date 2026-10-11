"""Mapping between our neutral types and the Responses API, tested offline on SDK objects."""

from typing import Any

from openai.types.responses import Response

from voice_order.textmode.llm import (
    AssistantMessage,
    ToolCall,
    ToolOutput,
    ToolSpec,
    Usage,
    UserMessage,
)
from voice_order.textmode.openai_client import parse, to_input, to_tools
from voice_order.tools.catalog import TOOLS


def response(*output: dict[str, Any], usage: tuple[int, int] | None = (50, 7)) -> Response:
    """A real SDK Response object, validated from JSON shaped like the API's."""
    data: dict[str, Any] = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-6-luna",
        "output": list(output),
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }
    if usage:
        data["usage"] = {
            "input_tokens": usage[0],
            "output_tokens": usage[1],
            "total_tokens": sum(usage),
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
    return Response.model_validate(data)


def message(*parts: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": list(parts),
    }


def text(t: str) -> dict[str, Any]:
    return {"type": "output_text", "text": t, "annotations": []}


def function_call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": "completed",
    }


# --- requests ------------------------------------------------------------------------


def test_messages_become_input_items() -> None:
    items = to_input(
        [
            AssistantMessage("Hi, what would you like?"),
            UserMessage("A dosa"),
            ToolCall("c1", "search_menu", '{"query":"dosa"}'),
            ToolOutput("c1", '{"ok":true}'),
        ]
    )
    assert items == [
        {"type": "message", "role": "assistant", "content": "Hi, what would you like?"},
        {"type": "message", "role": "user", "content": "A dosa"},
        {
            "type": "function_call",
            "call_id": "c1",
            "name": "search_menu",
            "arguments": '{"query":"dosa"}',
        },
        {"type": "function_call_output", "call_id": "c1", "output": '{"ok":true}'},
    ]


def test_tools_are_sent_with_their_generated_schemas() -> None:
    specs = [ToolSpec.from_tool(t) for t in TOOLS.values()]
    tools = to_tools(specs)
    assert [t["name"] for t in tools] == list(TOOLS)
    search = tools[0]
    assert search["type"] == "function"
    assert search["strict"] is False
    assert search["parameters"] == TOOLS["search_menu"].parameters_schema()


# --- responses ------------------------------------------------------------------------


def test_parse_text_reply() -> None:
    reply = parse(response(message(text("What size would you like?"))))
    assert reply.text == "What size would you like?"
    assert reply.tool_calls == ()
    assert reply.usage == Usage(50, 7)


def test_parse_tool_calls_in_order() -> None:
    reply = parse(
        response(
            function_call("c1", "search_menu", '{"query":"dosa"}'),
            function_call("c2", "get_order_summary", "{}"),
        )
    )
    assert reply.text == ""
    assert reply.tool_calls == (
        ToolCall("c1", "search_menu", '{"query":"dosa"}'),
        ToolCall("c2", "get_order_summary", "{}"),
    )


def test_parse_text_and_tool_call_together() -> None:
    reply = parse(
        response(
            message(text("Let me check. "), text(" One moment.")),
            function_call("c1", "search_menu", '{"query":"cold coffee"}'),
        )
    )
    assert reply.text == "Let me check. One moment."
    assert len(reply.tool_calls) == 1


def test_parse_refusal_is_spoken_text() -> None:
    reply = parse(response(message({"type": "refusal", "refusal": "I can't help with that."})))
    assert reply.text == "I can't help with that."


def test_parse_without_usage() -> None:
    assert parse(response(message(text("Hi")), usage=None)).usage == Usage()
