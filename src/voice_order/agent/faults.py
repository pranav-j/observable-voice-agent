"""Seeded faults, for proving the eval harness catches what it claims to.

FAULT in the environment breaks one thing in the voice worker on purpose. Each fault
must push one eval metric past its limit; if it doesn't, the harness is blind to it.
The core (menu, order, tools) is never touched: the faults live in the voice layer.

    no_barge_in      the agent keeps talking when the caller speaks over it
    drop_modifiers   the voice tool layer quietly drops modifiers from add/update
    aggressive_eou   end-of-turn silence cut to 150 ms
    slow_llm         800 ms added before the LLM's first token
"""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any, TypeVar

SLOW_LLM_DELAY_S = 0.8

T = TypeVar("T")


async def delay_first(stream: AsyncIterable[T], seconds: float) -> AsyncIterator[T]:
    """Pass the stream through, holding back its first item by `seconds`."""
    first = True
    async for item in stream:
        if first and seconds > 0:
            await asyncio.sleep(seconds)
        first = False
        yield item


def without_modifiers(arguments: dict[str, Any]) -> dict[str, Any]:
    """The tool arguments with any modifiers silently removed."""
    if "modifier_ids" not in arguments:
        return arguments
    return {**arguments, "modifier_ids": []}
