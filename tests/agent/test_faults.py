"""Seeded faults: each breaks exactly one thing, and only when asked."""

import time
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError

from tests.textmode.fakes import CountingStore
from voice_order.agent.faults import delay_first, without_modifiers
from voice_order.agent.tools import livekit_tools
from voice_order.config import Settings
from voice_order.menu.models import Menu
from voice_order.tools.base import Session


async def _items(*values: str) -> AsyncIterator[str]:
    for v in values:
        yield v


async def test_delay_first_holds_back_only_the_first_item() -> None:
    started = time.perf_counter()
    stamps = []
    async for _ in delay_first(_items("a", "b", "c"), 0.05):
        stamps.append(time.perf_counter() - started)
    assert stamps[0] >= 0.05
    assert stamps[-1] - stamps[0] < 0.05


async def test_no_delay_passes_straight_through() -> None:
    assert [x async for x in delay_first(_items("a", "b"), 0.0)] == ["a", "b"]


def test_without_modifiers() -> None:
    args = {"item_id": "cold_coffee", "modifier_ids": ["oat_milk"]}
    assert without_modifiers(args) == {"item_id": "cold_coffee", "modifier_ids": []}
    assert without_modifiers({"line_id": 1}) == {"line_id": 1}


@pytest.mark.parametrize(("drop", "expected"), [(False, ["oat_milk"]), (True, [])])
async def test_tool_layer_drops_modifiers_only_under_the_fault(
    menu: Menu, drop: bool, expected: list[str]
) -> None:
    session = Session.start(menu, "fault-test")
    tools = {t.info.name: t for t in livekit_tools(session, CountingStore(), drop_modifiers=drop)}
    await tools["add_item"](
        raw_arguments={
            "item_id": "cold_coffee",
            "quantity": 1,
            "size_id": "large",
            "modifier_ids": ["oat_milk"],
        }
    )
    assert session.order.lines[0].modifier_ids == expected


def test_no_fault_by_default() -> None:
    s = Settings(_env_file=None)
    assert s.fault == "none"
    assert s.effective_eou_silence_ms == s.eou_silence_ms


def test_aggressive_eou_cuts_the_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULT", "aggressive_eou")
    s = Settings(_env_file=None)
    assert s.effective_eou_silence_ms == 150
    assert s.voice_config()["eou_silence_ms"] == 150
    assert s.voice_config()["fault"] == "aggressive_eou"


def test_unknown_fault_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULT", "everything")
    with pytest.raises(ValidationError, match="fault"):
        Settings(_env_file=None)
