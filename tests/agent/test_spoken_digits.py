"""Phone numbers spoken one digit at a time, prices left alone."""

from collections.abc import AsyncIterator

import pytest

from voice_order.agent.spoken_digits import digits_one_by_one, spoken_digits


@pytest.mark.parametrize(
    ("text", "spoken"),
    [
        ("Your number is 98765 23456.", "Your number is 9 8 7 6 5, 2 3 4 5 6."),
        ("It's 9876523456, right?", "It's 9 8 7 6 5, 2 3 4 5 6, right?"),
        ("Call 98765-23456 back.", "Call 9 8 7 6 5, 2 3 4 5 6 back."),
        ("Your total is 1,160 rupees.", "Your total is 1,160 rupees."),
        ("One Cold Coffee, 220 rupees.", "One Cold Coffee, 220 rupees."),
    ],
)
def test_long_numbers_are_spaced_out(text: str, spoken: str) -> None:
    assert digits_one_by_one(text) == spoken


async def _stream(*chunks: str) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


async def _spoken(*chunks: str) -> str:
    return "".join([c async for c in spoken_digits(_stream(*chunks))])


async def test_a_number_split_across_chunks_is_still_spaced_out() -> None:
    chunks = ("The order is for Priya, phone number 987", "65 234", "56. Is that correct?")
    assert await _spoken(*chunks) == (
        "The order is for Priya, phone number 9 8 7 6 5, 2 3 4 5 6. Is that correct?"
    )


async def test_text_without_numbers_passes_through() -> None:
    assert await _spoken("Anything ", "else?") == "Anything else?"


async def test_a_number_at_the_very_end_comes_out() -> None:
    assert await _spoken("Your number is ", "98765 23456") == "Your number is 9 8 7 6 5, 2 3 4 5 6"
