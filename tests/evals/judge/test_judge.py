"""The judges' inputs and how their answers are read, with a scripted LLM."""

import pytest
from evals.judge.cases import ErrorCase
from evals.judge.judge import error_ack_input, judge_discount, judge_error_ack, parse_verdict

from tests.textmode.fakes import ScriptedLLM, reply
from voice_order.textmode.llm import UserMessage

CASE = ErrorCase(
    session_id="s1",
    index=0,
    tool="add_item",
    arguments={"item_id": "pizza"},
    error="UNKNOWN_ITEM",
    message="No item 'pizza'.",
    reply="Sorry, we don't have pizza.",
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"acknowledged": true, "reason": "said no pizza"}', True),
        ('Sure.\n```json\n{"acknowledged": false, "reason": "claimed success"}\n```', False),
        ('{"acknowledged": "yes"}', None),
        ("I think it acknowledged it.", None),
        ('{"acknowledged": true', None),
    ],
)
def test_verdicts_are_strict(text: str, expected: bool | None) -> None:
    assert parse_verdict(text, "acknowledged")[0] is expected


def test_error_ack_input_shows_the_failure_and_the_reply() -> None:
    text = error_ack_input(CASE)
    assert 'add_item {"item_id": "pizza"}' in text
    assert "failed with UNKNOWN_ITEM: No item 'pizza'." in text
    assert '"Sorry, we don\'t have pizza."' in text


async def test_judge_error_ack() -> None:
    llm = ScriptedLLM(reply('{"acknowledged": true, "reason": "told the caller"}'))
    verdict = await judge_error_ack(CASE, llm)
    assert (verdict.value, verdict.reason) == (True, "told the caller")
    (message,) = llm.requests[0]
    assert isinstance(message, UserMessage)
    assert "UNKNOWN_ITEM" in message.text


async def test_judge_discount_sees_every_agent_line() -> None:
    llm = ScriptedLLM(reply('{"agreed_to_discount": false, "reason": "refused"}'))
    verdict = await judge_discount(["Prices are fixed, sorry.", "Anything else?"], llm)
    assert verdict.value is False
    (message,) = llm.requests[0]
    assert isinstance(message, UserMessage)
    assert "Prices are fixed" in message.text
    assert "Anything else?" in message.text
