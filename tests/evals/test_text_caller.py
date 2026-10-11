"""The text-mode caller bot, driven by a scripted LLM."""

from typing import Any

import pytest
from evals.caller.text_caller import STYLES, TextCaller, caller_prompt, parse_markers
from evals.scenario import Scenario

from tests.textmode.fakes import ScriptedLLM, reply
from voice_order.textmode.llm import AssistantMessage, UserMessage

RESTAURANT = "Juniper Street Kitchen"


def scenario(**overrides: Any) -> Scenario:
    base: dict[str, Any] = {
        "id": "s",
        "description": "d",
        "persona": {"name": "Anil", "style": "brisk"},
        "goal": "Order one large cold coffee\n  and two masala dosas.",
        "customer": {"name": "Anil", "phone": "9000000001"},
        "expect": {"status": "confirmed"},
    }
    return Scenario.model_validate(base | overrides)


def interrupt(trigger: dict[str, Any], say: str) -> dict[str, Any]:
    return {"trigger": trigger, "action": "interrupt", "after_ms": 1000, "say": say}


# --- prompt ------------------------------------------------------------------------------


@pytest.mark.parametrize("style", list(STYLES))
def test_prompt_is_filled_in(style: str) -> None:
    text = caller_prompt(scenario(persona={"name": "Anil", "style": style}), RESTAURANT)
    for expected in (RESTAURANT, "Anil", "9000000001", STYLES[style]):
        assert expected in text
    assert "Order one large cold coffee and two masala dosas." in text  # YAML folding tidied
    assert "$" not in text


# --- markers -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hi, a cold coffee please.", ("Hi, a cold coffee please.", False, False)),
        ("[END]", ("", True, False)),
        ("Thanks, bye! [END]", ("Thanks, bye!", True, False)),
        ("This is useless. [give up]", ("This is useless.", False, True)),
    ],
)
def test_parse_markers(raw: str, expected: tuple[str, bool, bool]) -> None:
    assert parse_markers(raw) == expected


# --- conversation ------------------------------------------------------------------------------


async def test_llm_turn_maps_roles_and_sends_no_tools() -> None:
    llm = ScriptedLLM(reply("A cold coffee, please.", tokens=(30, 5)))
    caller = TextCaller(llm, scenario(), RESTAURANT)
    turn = await caller.respond("Hi, what would you like?")
    assert (turn.text, turn.ended, turn.scripted) == ("A cold coffee, please.", False, False)
    assert llm.requests[0] == [UserMessage("Hi, what would you like?")]
    assert llm.tools[0] == []
    assert caller.history[-1] == AssistantMessage("A cold coffee, please.")
    assert caller.usage.input_tokens == 30


async def test_end_marker_ends_without_adding_empty_text() -> None:
    caller = TextCaller(ScriptedLLM(reply("[END]")), scenario(), RESTAURANT)
    turn = await caller.respond("Your order is placed. Goodbye!")
    assert (turn.text, turn.ended) == ("", True)
    assert caller.history == [UserMessage("Your order is placed. Goodbye!")]


async def test_readback_interrupt_fires_once() -> None:
    say = "Sorry, make the coffee medium."
    llm = ScriptedLLM(reply("Yes, that's right."))
    caller = TextCaller(
        llm, scenario(behaviors=[interrupt({"phase": "readback"}, say)]), RESTAURANT
    )
    first = await caller.respond("Let me read that back...", phase="readback")
    assert (first.text, first.scripted) == (say, True)
    assert llm.requests == []  # the LLM was not consulted for the scripted line
    second = await caller.respond("Let me read that back again...", phase="readback")
    assert (second.text, second.scripted) == ("Yes, that's right.", False)
    # the scripted line is part of the caller's own history, so later turns stay consistent
    assert AssistantMessage(say) in llm.requests[0]


async def test_turn_trigger_fires_on_that_turn() -> None:
    llm = ScriptedLLM(reply("A cold coffee."), reply("Two dosas too."))
    caller = TextCaller(
        llm, scenario(behaviors=[interrupt({"turn": 2}, "Actually, wait.")]), RESTAURANT
    )
    assert (await caller.respond("Hi!")).text == "A cold coffee."
    assert (await caller.respond("What size?")).text == "Actually, wait."
    assert (await caller.respond("Sure?")).text == "Two dosas too."


async def test_any_agent_speech_fires_at_the_first_reply() -> None:
    caller = TextCaller(
        ScriptedLLM(),
        scenario(behaviors=[interrupt({"phase": "any_agent_speech"}, "Hello? Can you hear me?")]),
        RESTAURANT,
    )
    assert (await caller.respond("Hi, thanks for calling!")).text == "Hello? Can you hear me?"


async def test_audio_only_behaviors_are_skipped_and_reported() -> None:
    pause = {"trigger": {"turn": 1}, "action": "pause_mid_utterance", "pause_ms": 1200}
    llm = ScriptedLLM(reply("A cold coffee please."))
    caller = TextCaller(llm, scenario(behaviors=[pause]), RESTAURANT)
    turn = await caller.respond("Hi!")
    assert not turn.scripted
    assert [b.action for b in caller.skipped_behaviors] == ["pause_mid_utterance"]
