"""LLMClient on OpenAI's Responses API."""

from collections.abc import Sequence

from openai import AsyncOpenAI
from openai.types.responses import FunctionToolParam, Response, ResponseInputItemParam
from openai.types.shared import ReasoningEffort

from voice_order.config import Settings
from voice_order.textmode.llm import (
    AssistantMessage,
    LLMReply,
    Message,
    ToolCall,
    ToolOutput,
    ToolSpec,
    Usage,
    UserMessage,
)


def to_input(messages: Sequence[Message]) -> list[ResponseInputItemParam]:
    """Our neutral messages as Responses API input items."""
    items: list[ResponseInputItemParam] = []
    for m in messages:
        match m:
            case UserMessage(text=text):
                items.append({"type": "message", "role": "user", "content": text})
            case AssistantMessage(text=text):
                items.append({"type": "message", "role": "assistant", "content": text})
            case ToolCall(call_id=call_id, name=name, arguments=arguments):
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": name,
                        "arguments": arguments,
                    }
                )
            case ToolOutput(call_id=call_id, output=output):
                items.append({"type": "function_call_output", "call_id": call_id, "output": output})
    return items


def to_tools(specs: Sequence[ToolSpec]) -> list[FunctionToolParam]:
    # strict=False: our schemas have optional arguments with defaults, which OpenAI's strict
    # mode does not allow. dispatch validates every call anyway.
    return [
        {
            "type": "function",
            "name": s.name,
            "description": s.description,
            "parameters": s.parameters,
            "strict": False,
        }
        for s in specs
    ]


def parse(response: Response) -> LLMReply:
    texts: list[str] = []
    calls: list[ToolCall] = []
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                texts.append(part.text if part.type == "output_text" else part.refusal)
        elif item.type == "function_call":
            calls.append(ToolCall(call_id=item.call_id, name=item.name, arguments=item.arguments))
    usage = (
        Usage(response.usage.input_tokens, response.usage.output_tokens)
        if response.usage
        else Usage()
    )
    return LLMReply(
        text=" ".join(t.strip() for t in texts if t.strip()), tool_calls=tuple(calls), usage=usage
    )


class OpenAIClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        reasoning_effort: ReasoningEffort = "none",
        timeout_s: float = 30.0,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        # The SDK retries rate limits and transient errors (twice by default).
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_s)

    @classmethod
    def from_settings(cls, settings: Settings, model: str | None = None) -> "OpenAIClient":
        chosen = model or settings.llm_model
        # gpt-5-nano has no "none"; the caller and the judge stay on models that do.
        effort: ReasoningEffort = "minimal" if chosen == "gpt-5-nano" else "none"
        return cls(chosen, settings.openai_api_key.get_secret_value(), reasoning_effort=effort)

    async def complete(
        self, instructions: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMReply:
        response = await self._client.responses.create(
            model=self.model,
            instructions=instructions,
            input=to_input(messages),
            tools=to_tools(tools),
            reasoning={"effort": self.reasoning_effort},
            store=False,  # we keep the conversation ourselves and resend it each time
        )
        return parse(response)
