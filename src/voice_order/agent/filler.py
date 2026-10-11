"""Filler phrases: say "One moment." while the agent is still working on a reply.

When a reply needs tool calls, the caller hears nothing until the LLM has run once or
twice and text-to-speech has started. A short filler fills that silence. It goes out as
the start of the same reply: a separate utterance would queue behind the reply and play
after it.
"""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Callable
from itertools import cycle
from typing import Any

FILLERS = ("One moment.", "Just a second.", "Let me check that.")


def fillers() -> Callable[[], str]:
    """A different filler each time, in a fixed order."""
    phrases = cycle(FILLERS)
    return lambda: next(phrases)


async def with_filler(
    stream: AsyncIterable[Any],
    *,
    after: float,
    filler: str,
    starts_tool_call: Callable[[Any], bool],
) -> AsyncIterator[Any]:
    """Pass the stream through, saying `filler` first if the reply is slow to start.

    Slow means no first chunk within `after` seconds, or a first chunk that's a tool
    call, since a tool round and another LLM step are still to come.
    """
    iterator = aiter(stream)
    first = asyncio.ensure_future(anext(iterator))
    try:
        done, _ = await asyncio.wait({first}, timeout=after)
        said = not done
        if said:
            yield filler
        try:
            chunk = await first
        except StopAsyncIteration:
            return
        if not said and starts_tool_call(chunk):
            yield filler
        yield chunk
        async for chunk in iterator:
            yield chunk
    finally:
        if not first.done():
            first.cancel()
