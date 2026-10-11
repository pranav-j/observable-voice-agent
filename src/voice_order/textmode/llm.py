"""Provider-neutral LLM types. Each provider client translates these to its own API."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from voice_order.tools.base import Tool


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    text: str


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str  # raw JSON, exactly as the model produced it


@dataclass(frozen=True)
class ToolOutput:
    call_id: str
    output: str  # JSON result sent back to the model


Message = UserMessage | AssistantMessage | ToolCall | ToolOutput


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

    @classmethod
    def from_tool(cls, tool: Tool[Any]) -> "ToolSpec":
        return cls(tool.name, tool.description, tool.parameters_schema())


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True)
class LLMReply:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = Usage()


class LLMClient(Protocol):
    model: str

    async def complete(
        self, instructions: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMReply:
        """One model call. Text and tool calls may both be present in the reply."""
        ...
