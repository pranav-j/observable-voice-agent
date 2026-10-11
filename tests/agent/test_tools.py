"""The LiveKit tool adapter: same schemas, same dispatch, JSON results, saves on change."""

import json
from typing import Any

import pytest
from livekit.agents.llm import ChatChunk, ChoiceDelta

from tests.textmode.fakes import CountingStore
from voice_order.agent.tools import StepText, livekit_tools
from voice_order.menu.models import Menu
from voice_order.tools.base import Result, Session
from voice_order.tools.catalog import TOOLS


@pytest.fixture
def session(menu: Menu) -> Session:
    return Session.start(menu, "voice-test")


def by_name(tools: list[Any]) -> dict[str, Any]:
    return {t.info.name: t for t in tools}


def test_one_tool_per_core_tool_with_the_same_schema(session: Session) -> None:
    tools = by_name(livekit_tools(session, CountingStore()))
    assert list(tools) == list(TOOLS)
    for name, tool in tools.items():
        schema = tool.info.raw_schema
        assert schema["description"] == TOOLS[name].description
        assert schema["parameters"] == TOOLS[name].parameters_schema()


async def test_change_is_saved_reported_and_returned_as_json(session: Session) -> None:
    store = CountingStore()
    seen: list[tuple[str, Result]] = []

    async def listener(name: str, result: Result) -> None:
        seen.append((name, result))

    tools = by_name(livekit_tools(session, store, listener))
    out = await tools["add_item"](raw_arguments={"item_id": "masala_dosa", "quantity": 2})
    result = json.loads(out.output)  # JSON, not a Python repr
    assert out.reply_required is True  # no question was asked, so the agent replies next
    assert result["ok"] is True
    assert session.order.lines[0].item_id == "masala_dosa"
    assert await store.get("voice-test") == session.order
    assert seen == [("add_item", result)]


async def test_reading_does_not_save(session: Session) -> None:
    store = CountingStore()
    tools = by_name(livekit_tools(session, store))
    result = json.loads((await tools["search_menu"](raw_arguments={"query": "dosa"})).output)
    assert result["matches"]
    assert store.saves == 0


async def test_errors_come_back_as_data(session: Session) -> None:
    store = CountingStore()
    tools = by_name(livekit_tools(session, store))
    out = await tools["add_item"](raw_arguments={"item_id": "pizza", "quantity": 1})
    result = json.loads(out.output)
    assert (result["ok"], result["error"]) == (False, "UNKNOWN_ITEM")
    assert store.saves == 0


async def test_arguments_are_validated_like_text_mode(session: Session) -> None:
    # LiveKit passes raw arguments through unchecked; dispatch does the validating.
    tools = by_name(livekit_tools(session, CountingStore()))
    result = json.loads((await tools["add_item"](raw_arguments={"item_id": "masala_dosa"})).output)
    assert result["error"] == "INVALID_ARGUMENTS"


# --- the turn-taking rule, in voice ------------------------------------------------------


def asked(text: str) -> StepText:
    step = StepText()
    step.add(text)
    return step


async def test_after_a_question_order_changes_run_but_the_turn_ends(session: Session) -> None:
    tools = by_name(livekit_tools(session, CountingStore(), step=asked("Added. Anything else?")))
    out = await tools["add_item"](raw_arguments={"item_id": "masala_dosa", "quantity": 1})
    assert json.loads(out.output)["ok"] is True
    assert out.reply_required is False  # the caller speaks next


@pytest.mark.parametrize("name", ["end_call", "transfer_to_human", "confirm_order", "get_readback"])
async def test_after_a_question_final_actions_wait(session: Session, name: str) -> None:
    tools = by_name(livekit_tools(session, CountingStore(), step=asked("What's your number?")))
    args = (
        {"reason": "caller stopped responding"} if name in ("end_call", "transfer_to_human") else {}
    )
    out = await tools[name](raw_arguments=args)
    assert json.loads(out.output)["error"] == "WAITING_FOR_CALLER"
    assert out.reply_required is False
    assert session.ending is None
    assert session.order.status == "draft"


async def test_without_a_question_the_agent_may_carry_on(session: Session) -> None:
    tools = by_name(livekit_tools(session, CountingStore(), step=asked("Let me check that.")))
    out = await tools["search_menu"](raw_arguments={"query": "dosa"})
    assert out.reply_required is True


def test_step_text_collects_strings_and_chunks() -> None:
    step = StepText()
    step.add("Sure. ")
    step.add(ChatChunk(id="c1", delta=ChoiceDelta(role="assistant", content="What size?")))
    step.add(ChatChunk(id="c2", delta=None))
    assert step.text == "Sure. What size?"
    assert step.asked_caller
    step.reset()
    assert not step.asked_caller
