"""The LiveKit tool adapter: same schemas, same dispatch, JSON results, saves on change."""

import json
from typing import Any

import pytest

from tests.textmode.fakes import CountingStore
from voice_order.agent.tools import livekit_tools
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
    result = json.loads(out)  # JSON, not a Python repr
    assert result["ok"] is True
    assert session.order.lines[0].item_id == "masala_dosa"
    assert await store.get("voice-test") == session.order
    assert seen == [("add_item", result)]


async def test_reading_does_not_save(session: Session) -> None:
    store = CountingStore()
    tools = by_name(livekit_tools(session, store))
    result = json.loads(await tools["search_menu"](raw_arguments={"query": "dosa"}))
    assert result["matches"]
    assert store.saves == 0


async def test_errors_come_back_as_data(session: Session) -> None:
    store = CountingStore()
    tools = by_name(livekit_tools(session, store))
    result = json.loads(await tools["add_item"](raw_arguments={"item_id": "pizza", "quantity": 1}))
    assert (result["ok"], result["error"]) == (False, "UNKNOWN_ITEM")
    assert store.saves == 0


async def test_arguments_are_validated_like_text_mode(session: Session) -> None:
    # LiveKit passes raw arguments through unchecked; dispatch does the validating.
    tools = by_name(livekit_tools(session, CountingStore()))
    result = json.loads(await tools["add_item"](raw_arguments={"item_id": "masala_dosa"}))
    assert result["error"] == "INVALID_ARGUMENTS"
