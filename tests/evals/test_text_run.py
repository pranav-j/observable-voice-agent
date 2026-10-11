"""One full scenario run with both sides scripted: no network, fully deterministic."""

from collections.abc import Sequence
from typing import Any

import pytest
from evals.scenario import SCENARIO_DIR, Scenario, load_scenario
from evals.text_run import RunResult, run_text_scenario

from tests.evals.scripts import HAPPY_AGENT, HAPPY_CALLER
from tests.textmode.fakes import ScriptedLLM, call, reply
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


async def test_barge_in_during_readback_changes_the_order(menu: Menu) -> None:
    barge = load_scenario(SCENARIO_DIR / "readback_barge_in_size_change.yaml")
    agent = [
        reply(
            "",
            call("add_item", item_id="cold_coffee", quantity=1, size_id="large"),
            call("add_item", item_id="masala_dosa", quantity=2),
            call("set_customer", name="Anil", phone="9000000001"),
            call("get_readback"),
        ),
        reply("Let me read that back. ... Is that correct?"),
        reply("", call("update_item", line_id=1, size_id="medium"), call("get_readback")),
        reply("Sure. Let me read that back again. ... Is that correct?"),
        reply("", call("confirm_order")),
        reply("Ready for pickup. Goodbye!"),
    ]
    caller = [
        reply("A large cold coffee and two masala dosas. I'm Anil, 9000000001."),
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
