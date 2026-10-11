"""One full scenario run with both sides scripted: no network, fully deterministic."""

from collections.abc import Sequence
from typing import Any

import pytest
from evals.scenario import SCENARIO_DIR, Scenario, load_scenario
from evals.text_run import RunResult, run_text_scenario

from tests.evals.scripts import HAPPY_AGENT, HAPPY_CALLER
from tests.textmode.fakes import ScriptedLLM, ScriptLine, call, readback_text, reply
from voice_order.menu.models import Menu
from voice_order.store.base import InMemoryOrderStore
from voice_order.textmode.llm import LLMReply, Message, ToolSpec

HAPPY = load_scenario(SCENARIO_DIR / "happy_path_single_coffee.yaml")


def scenario(**overrides: Any) -> Scenario:
    return HAPPY.model_copy(update=overrides)


async def play(
    menu: Menu, sc: Scenario, agent: Sequence[LLMReply], caller: Sequence[LLMReply]
) -> tuple[RunResult, InMemoryOrderStore]:
    store = InMemoryOrderStore()
    result = await run_text_scenario(
        sc,
        1,
        menu=menu,
        store=store,
        agent_llm=ScriptedLLM(*agent),
        caller_llm=ScriptedLLM(*caller),
    )
    return result, store


async def test_happy_path_is_scored_as_a_success(menu: Menu) -> None:
    result, store = await play(menu, HAPPY, HAPPY_AGENT, HAPPY_CALLER)
    assert result.end_reason == "caller_ended"
    assert result.error is None
    assert result.turns == 3
    assert result.score.task_success
    assert result.score.exact_match
    saved = await store.get(result.session_id)
    assert saved is not None
    assert saved.status == "confirmed"
    # transcript: greeting, then caller/agent pairs, then the caller's goodbye
    speakers = [e.speaker for e in result.transcript]
    assert speakers == ["agent", "caller", "agent", "caller", "agent", "caller", "agent", "caller"]
    assert result.transcript[2].tool_calls[0]["name"] == "add_item"
    assert result.transcript[-1].text == "Thanks, bye!"
    # usage is kept per side
    assert result.agent_usage.input_tokens > result.caller_usage.input_tokens > 0
    assert (result.agent_model, result.caller_model) == ("scripted", "scripted")
    assert result.session_id.startswith("eval-happy_path_single_coffee-r1-")
    assert result.confirmed_before_reply == 0


async def test_barge_in_during_readback_changes_the_order(menu: Menu) -> None:
    barge = load_scenario(SCENARIO_DIR / "readback_barge_in_size_change.yaml")
    large: ScriptLine = ("cold_coffee", 1, "large", [])
    medium: ScriptLine = ("cold_coffee", 1, "medium", [])
    dosas: ScriptLine = ("masala_dosa", 2, None, [])
    agent = [
        reply(
            "",
            call("add_item", item_id="cold_coffee", quantity=1, size_id="large"),
            call("add_item", item_id="masala_dosa", quantity=2),
            call("set_customer", name="Anil", phone="9000012345"),
            call("get_readback"),
        ),
        reply(readback_text(large, dosas, name="Anil", phone="9000012345")),
        reply("", call("update_item", line_id=1, size_id="medium"), call("get_readback")),
        reply("Sure. " + readback_text(medium, dosas, name="Anil", phone="9000012345")),
        reply("", call("confirm_order")),
        reply("Ready for pickup. Goodbye!"),
    ]
    caller = [
        reply("A large cold coffee and two masala dosas. I'm Anil, 9000012345."),
        # turn 2 is the read-back: the scripted interrupt speaks, the LLM is not asked
        reply("Yes, that's correct."),
        reply("[END]"),
    ]
    result, _ = await play(menu, barge, agent, caller)
    scripted = [e for e in result.transcript if e.scripted]
    assert [e.text for e in scripted] == ["Sorry, make the coffee medium."]
    assert result.score.task_success, result.score.mismatches
    assert result.skipped_behaviors == ["pause_mid_utterance"]


async def test_caller_giving_up_is_a_failure(menu: Menu) -> None:
    result, _ = await play(
        menu, HAPPY, agent=[], caller=[reply("This is going nowhere. [GIVE UP]")]
    )
    assert result.end_reason == "caller_gave_up"
    assert result.score.status == "abandoned"
    assert not result.score.task_success


async def test_max_turns(menu: Menu) -> None:
    result, _ = await play(
        menu,
        scenario(max_turns=2),
        agent=[reply("Sorry, could you repeat that?"), reply("Sorry?")],
        caller=[reply("Umm."), reply("Hmm.")],
    )
    assert (result.end_reason, result.turns) == ("max_turns", 2)
    assert not result.score.task_success


@pytest.mark.parametrize(
    ("tool", "end_reason", "status"),
    [("end_call", "agent_ended", "abandoned"), ("transfer_to_human", "transferred", "escalated")],
)
async def test_agent_ending_the_call(menu: Menu, tool: str, end_reason: str, status: str) -> None:
    result, _ = await play(
        menu,
        HAPPY,
        agent=[reply("", call(tool, reason="test")), reply("Goodbye.")],
        caller=[reply("I want to speak to a person.")],
    )
    assert result.end_reason == end_reason
    assert result.score.status == status


class FailingLLM:
    model = "failing"

    async def complete(
        self, instructions: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> LLMReply:
        raise RuntimeError("API is down")


async def test_errors_are_recorded_and_the_order_still_closed(menu: Menu) -> None:
    store = InMemoryOrderStore()
    result = await run_text_scenario(
        HAPPY,
        2,
        menu=menu,
        store=store,
        agent_llm=FailingLLM(),
        caller_llm=ScriptedLLM(reply("A cold coffee, please.")),
    )
    assert result.end_reason == "error"
    assert result.error == "RuntimeError: API is down"
    assert result.score.status == "abandoned"


async def test_results_serialize_to_json(menu: Menu) -> None:
    result, _ = await play(menu, HAPPY, HAPPY_AGENT, HAPPY_CALLER)
    assert RunResult.model_validate_json(result.model_dump_json()) == result


async def test_confirming_in_the_readback_turn_is_counted(menu: Menu) -> None:
    agent = [
        reply(
            "",
            call(
                "add_item",
                item_id="cold_coffee",
                quantity=1,
                size_id="large",
                modifier_ids=["oat_milk"],
            ),
            call("set_customer", name="Priya", phone="9000023456"),
            call("get_readback"),
            call("confirm_order"),
        ),
        reply("Let me read that back. ... Is that correct? Your order is placed."),
    ]
    caller = [
        reply("One large cold coffee with oat milk. Priya, 9000023456."),
        reply("[END]"),
    ]
    result, _ = await play(menu, HAPPY, agent, caller)
    # Still counted: the metric measures the attempt...
    assert result.confirmed_before_reply == 1
    # ...but the code guard stops it, so the order isn't placed without the caller's yes.
    confirm = result.transcript[2].tool_calls[-1]
    assert (confirm["name"], confirm["ok"], confirm.get("error")) == (
        "confirm_order",
        False,
        "READBACK_NOT_ANSWERED",
    )
    assert not result.score.task_success


# --- the caller's last words, and hanging up early --------------------------------------------


async def test_a_final_yes_with_goodbye_still_confirms(menu: Menu) -> None:
    agent = [
        *HAPPY_AGENT[:4],  # add the coffee, ask details, set customer + read back
        reply("", call("confirm_order")),
        reply("It'll be ready for pickup. Goodbye!"),
    ]
    caller = [
        reply("One large cold coffee with oat milk, please."),
        reply("Priya, 9000023456."),
        reply("Yes, that's correct. Goodbye. [END]"),  # yes and hang up in one breath
    ]
    result, _ = await play(menu, HAPPY, agent, caller)
    assert result.end_reason == "caller_ended"
    assert result.score.task_success
    assert result.transcript[-1].tool_calls[0]["name"] == "confirm_order"


async def test_silent_early_hang_up_gets_its_own_label(menu: Menu) -> None:
    result, _ = await play(menu, HAPPY, agent=[], caller=[reply("[END]")])
    assert result.end_reason == "caller_hung_up_early"
    assert result.score.status == "abandoned"
    assert not result.score.task_success  # still a failure; the label says whose


async def test_parting_words_reach_the_agent_before_an_early_hang_up(menu: Menu) -> None:
    result, _ = await play(
        menu,
        HAPPY,
        agent=[reply("Sure, what size?"), reply("No problem. Goodbye.")],
        caller=[reply("A cold coffee, please."), reply("Actually, never mind. [END]")],
    )
    assert result.end_reason == "caller_hung_up_early"
    assert result.transcript[-1].text == "No problem. Goodbye."
    assert result.turns == 2
