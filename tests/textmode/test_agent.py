"""The agent loop, driven by a scripted LLM. The LLM is faked; the loop is real."""

import json
from typing import Any

import pytest

from tests.textmode.fakes import GREETING, CountingStore, ScriptedLLM, call, reply
from voice_order.menu.models import Menu
from voice_order.textmode.agent import FALLBACK, CallEndedError, TextAgent
from voice_order.textmode.llm import AssistantMessage, Message, ToolOutput, Usage, UserMessage
from voice_order.tools.base import CallEnd, Session
from voice_order.tools.catalog import TOOLS


@pytest.fixture
def store() -> CountingStore:
    return CountingStore()


async def make_agent(menu: Menu, store: CountingStore, llm: ScriptedLLM, **kw: Any) -> TextAgent:
    agent = TextAgent(
        llm=llm,
        session=Session.start(menu, "t1"),
        store=store,
        instructions="SYSTEM",
        **kw,
    )
    await agent.start(GREETING)
    return agent


def outputs(messages: list[Message]) -> list[dict[str, Any]]:
    return [json.loads(m.output) for m in messages if isinstance(m, ToolOutput)]


# --- start and plain replies ------------------------------------------------------------


async def test_start_saves_the_empty_order_and_greets(menu: Menu, store: CountingStore) -> None:
    agent = await make_agent(menu, store, ScriptedLLM())
    assert agent.history == [AssistantMessage(GREETING)]
    assert await store.get("t1") == agent.session.order
    assert store.saves == 1


async def test_plain_reply(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(reply("What size would you like?"))
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("A cappuccino please")
    assert (turn.text, turn.tool_events, turn.ending, turn.hit_tool_limit) == (
        "What size would you like?",
        (),
        None,
        False,
    )
    assert llm.requests[0] == [AssistantMessage(GREETING), UserMessage("A cappuccino please")]


async def test_instructions_and_every_tool_are_sent(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(reply("Sure."))
    agent = await make_agent(menu, store, llm)
    await agent.respond("hi")
    assert llm.instructions == ["SYSTEM"]
    assert [t.name for t in llm.tools[0]] == list(TOOLS)


# --- tool calls ------------------------------------------------------------------------


async def test_tool_call_then_answer(menu: Menu, store: CountingStore) -> None:
    add = call("add_item", item_id="masala_dosa", quantity=2)
    llm = ScriptedLLM(reply("", add), reply("Two masala dosa, got it."))
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("Two masala dosas")

    assert turn.text == "Two masala dosa, got it."
    (event,) = turn.tool_events
    assert (event.name, event.result["ok"]) == ("add_item", True)
    assert event.duration_ms >= 0
    # the order changed, so it was saved
    assert agent.session.order.lines[0].item_id == "masala_dosa"
    assert await store.get("t1") == agent.session.order
    # the second request carries the call and its result back to the model
    second = llm.requests[1]
    assert second[-2] == add
    assert outputs(second)[-1]["ok"] is True


async def test_several_calls_in_one_reply_run_in_order(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(
        reply(
            "",
            call("add_item", item_id="affogato", quantity=1),
            call("set_customer", name="Anil", phone="9000000001"),
        ),
        reply("Done."),
    )
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("One affogato, I'm Anil, 9000000001")
    assert [e.name for e in turn.tool_events] == ["add_item", "set_customer"]
    assert agent.session.order.customer is not None
    assert store.saves == 3  # start + two changes


async def test_tool_errors_go_back_to_the_model(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(reply("", call("add_item", item_id="pizza", quantity=1)), reply("No pizza."))
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("A pizza")
    assert turn.tool_events[0].result["error"] == "UNKNOWN_ITEM"
    assert outputs(llm.requests[1])[-1]["error"] == "UNKNOWN_ITEM"
    assert agent.session.order.lines == []
    assert store.saves == 1  # nothing changed, nothing saved


async def test_unknown_tool_is_reported_not_raised(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(reply("", call("make_pizza")), reply("Sorry."))
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("Make me a pizza")
    assert turn.tool_events[0].result["error"] == "UNKNOWN_TOOL"


async def test_read_only_tools_do_not_save(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(reply("", call("search_menu", query="dosa")), reply("We have dosas."))
    agent = await make_agent(menu, store, llm)
    await agent.respond("Do you have dosa?")
    assert store.saves == 1


async def test_text_alongside_tool_calls_is_kept(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(
        reply("Let me check.", call("search_menu", query="cold coffee")),
        reply("Yes, we have cold coffee."),
    )
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("Cold coffee?")
    assert turn.text == "Let me check. Yes, we have cold coffee."


async def test_tool_round_limit_stops_a_runaway_model(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(*[reply("", call("search_menu", query="dosa")) for _ in range(3)])
    agent = await make_agent(menu, store, llm, max_tool_rounds=3)
    turn = await agent.respond("dosa")
    assert turn.hit_tool_limit
    assert turn.text == FALLBACK
    assert len(llm.requests) == 3
    assert agent.history[-1] == AssistantMessage(FALLBACK)


# --- ending and usage ----------------------------------------------------------------------


async def test_end_call_ends_the_conversation(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(reply("", call("end_call", reason="caller left")), reply("Goodbye!"))
    agent = await make_agent(menu, store, llm)
    turn = await agent.respond("Never mind, bye")
    assert turn.ending == CallEnd(kind="end_call", reason="caller left")
    assert turn.text == "Goodbye!"
    saved = await store.get("t1")
    assert saved is not None
    assert saved.status == "abandoned"
    with pytest.raises(CallEndedError):
        await agent.respond("Wait, one more thing")


async def test_usage_is_summed_per_turn_and_per_call(menu: Menu, store: CountingStore) -> None:
    llm = ScriptedLLM(
        reply("", call("search_menu", query="dosa"), tokens=(100, 5)),
        reply("We have dosas.", tokens=(120, 8)),
        reply("Anything else?", tokens=(130, 4)),
    )
    agent = await make_agent(menu, store, llm)
    first = await agent.respond("dosa?")
    second = await agent.respond("ok")
    assert first.usage == Usage(220, 13)
    assert second.usage == Usage(130, 4)
    assert agent.usage == Usage(350, 17)


async def test_hang_up_abandons_and_saves(menu: Menu, store: CountingStore) -> None:
    agent = await make_agent(menu, store, ScriptedLLM())
    await agent.hang_up("caller hung up")
    await agent.hang_up("again")  # idempotent: the first reason stays
    assert agent.session.ending == CallEnd(kind="end_call", reason="caller hung up")
    saved = await store.get("t1")
    assert saved is not None
    assert saved.status == "abandoned"
    assert store.saves == 2
