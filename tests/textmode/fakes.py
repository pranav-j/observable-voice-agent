"""Test doubles for the text agent: a scripted LLM and a store that counts saves."""

import json
from collections.abc import Sequence
from itertools import count
from typing import Any

from voice_order.menu.loader import load_menu
from voice_order.order import state
from voice_order.order.models import Order
from voice_order.order.readback import build_readback
from voice_order.store.base import InMemoryOrderStore
from voice_order.textmode.llm import LLMReply, Message, ToolCall, ToolSpec, Usage

GREETING = "Hi, thanks for calling. What would you like to order?"
_ids = count(1)


def call(tool: str, /, **arguments: Any) -> ToolCall:
    return ToolCall(call_id=f"call_{next(_ids)}", name=tool, arguments=json.dumps(arguments))


ScriptLine = tuple[str, int, str | None, list[str]]  # item, quantity, size, modifiers


def readback_text(*lines: ScriptLine, name: str, phone: str) -> str:
    """The read-back a scripted agent has to say for this order, built like get_readback."""
    menu = load_menu()
    order = state.new_order("script")
    for item_id, quantity, size_id, modifier_ids in lines:
        order = state.add_line(order, menu, item_id, quantity, size_id, modifier_ids)
    return build_readback(state.set_customer(order, name, phone), menu).text


def reply(text: str = "", *calls: ToolCall, tokens: tuple[int, int] = (10, 2)) -> LLMReply:
    return LLMReply(text=text, tool_calls=calls, usage=Usage(*tokens))


class ScriptedLLM:
    """Returns scripted replies in order and records every request."""

    model = "scripted"

    def __init__(self, *replies: LLMReply) -> None:
        self.replies = list(replies)
        self.requests: list[list[Message]] = []
        self.instructions: list[str] = []
        self.tools: list[list[ToolSpec]] = []

    async def complete(
        self, instructions: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMReply:
        self.requests.append(list(messages))
        self.instructions.append(instructions)
        self.tools.append(list(tools))
        if not self.replies:
            raise AssertionError("LLM called more times than scripted")
        return self.replies.pop(0)


class CountingStore(InMemoryOrderStore):
    def __init__(self) -> None:
        super().__init__()
        self.saves = 0

    async def save(self, order: Order) -> None:
        self.saves += 1
        await super().save(order)
