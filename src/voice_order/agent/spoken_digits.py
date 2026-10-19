"""Phone numbers said one digit at a time.

Text-to-speech reads "98765 23456" as "ninety-eight thousand seven hundred sixty-five...",
which no caller can check against their number. So before the agent's text reaches the
voice, runs of five or more digits are spaced out: "9 8 7 6 5, 2 3 4 5 6". Prices never
match (they're written "1,160 rupees"), and the transcript and the read-back check keep
the original text: only what's spoken changes.
"""

import re
from collections.abc import AsyncIterable, AsyncIterator

# Five or more digits, possibly in groups split by a space or a hyphen: "98765 23456".
_NUMBER = re.compile(r"\d{5,}(?:[ -]\d+)*")
# What might still be the start of such a number when a chunk ends mid-stream.
_UNFINISHED = re.compile(r"[\d -]*$")


def _spell(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    groups = [" ".join(digits[i : i + 5]) for i in range(0, len(digits), 5)]
    return ", ".join(groups)


def digits_one_by_one(text: str) -> str:
    return _NUMBER.sub(_spell, text)


async def spoken_digits(stream: AsyncIterable[str]) -> AsyncIterator[str]:
    """The text stream with long numbers spaced out, holding back a chunk's trailing digits
    until the next chunk shows whether the number goes on."""
    pending = ""
    async for chunk in stream:
        pending += chunk
        tail = _UNFINISHED.search(pending)
        cut = tail.start() if tail else len(pending)
        if cut:
            yield digits_one_by_one(pending[:cut])
            pending = pending[cut:]
    if pending:
        yield digits_one_by_one(pending)
