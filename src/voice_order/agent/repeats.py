"""Drop a sentence that repeats the one just before it in the same reply.

Now and then the LLM returns the same question twice in one response, as two message
items: "What name should I put on the order?What name should I put on the order?". The
plugin streams the text of every item, so the caller heard it twice. Which item is the
intermediate one is only known after its text has streamed, so the fix works on the text:
it holds each sentence until it ends, then drops it if it's the same as the last one.
Text-to-speech waits for whole sentences anyway, so holding them costs no time.
"""

import re
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from livekit.agents.llm import ChatChunk

_SENTENCE_END = re.compile(r"[.?!]+")


def _text_only(chunk: Any) -> str | None:
    """The chunk's text, if text is all it carries."""
    if isinstance(chunk, str):
        return chunk
    delta = chunk.delta if isinstance(chunk, ChatChunk) else None
    if delta and delta.content and not delta.tool_calls and not delta.extra:
        return delta.content
    return None


def _same(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


async def without_repeats(stream: AsyncIterable[Any]) -> AsyncIterator[Any]:
    """Pass the stream through, minus any sentence identical to the one before it."""
    pending = ""  # text since the last sentence end
    last = ""  # the last whole sentence let through
    async for chunk in stream:
        text = _text_only(chunk)
        if text is None:  # tool calls, and the marker between two message items
            if pending:
                yield pending
                pending = ""
            yield chunk
            continue
        pending += text
        while match := _SENTENCE_END.search(pending):
            sentence, pending = pending[: match.end()], pending[match.end() :]
            if sentence.strip() and _same(sentence, last):
                continue
            if sentence.strip():
                last = sentence
            yield sentence
    if pending:
        yield pending
