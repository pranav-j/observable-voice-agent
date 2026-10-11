"""Filler phrases: said only when the reply is slow to start."""

import asyncio
from collections.abc import AsyncIterator

from voice_order.agent.filler import FILLERS, fillers, with_filler


async def _stream(*items: object, first_after: float = 0.0) -> AsyncIterator[object]:
    await asyncio.sleep(first_after)
    for item in items:
        yield item


def _is_call(chunk: object) -> bool:
    return chunk == "CALL"


async def _run(stream: AsyncIterator[object], after: float = 0.05) -> list[object]:
    out = with_filler(stream, after=after, filler="One moment.", starts_tool_call=_is_call)
    return [x async for x in out]


async def test_quick_text_gets_no_filler() -> None:
    assert await _run(_stream("Sure,", " one coffee.")) == ["Sure,", " one coffee."]


async def test_slow_first_chunk_gets_a_filler_first() -> None:
    assert await _run(_stream("Sure.", first_after=0.1)) == ["One moment.", "Sure."]


async def test_a_step_that_starts_with_a_tool_call_gets_a_filler() -> None:
    assert await _run(_stream("CALL")) == ["One moment.", "CALL"]


async def test_filler_said_once_even_if_slow_and_a_tool_call() -> None:
    assert await _run(_stream("CALL", first_after=0.1)) == ["One moment.", "CALL"]


async def test_empty_step_after_the_wait_only_says_the_filler() -> None:
    assert await _run(_stream(first_after=0.1)) == ["One moment."]


def test_fillers_rotate() -> None:
    nxt = fillers()
    assert [nxt() for _ in range(len(FILLERS) + 1)] == [*FILLERS, FILLERS[0]]
