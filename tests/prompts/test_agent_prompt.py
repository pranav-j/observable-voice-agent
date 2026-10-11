"""Structural checks on the agent prompt. How well it works is measured by the evals."""

import re
from typing import Any

import pytest

from voice_order.menu.models import Menu
from voice_order.prompts.loader import (
    AGENT_SYSTEM_VERSION,
    agent_system_prompt,
    greeting_prompt,
    load_prompt,
)
from voice_order.tools import catalog
from voice_order.tools.base import Session, dispatch
from voice_order.tools.catalog import TOOLS


@pytest.fixture(scope="module")
def text() -> str:
    return agent_system_prompt("Juniper Street Kitchen").text


def test_loads_with_version_and_restaurant(text: str) -> None:
    prompt = agent_system_prompt("Juniper Street Kitchen")
    assert (prompt.name, prompt.version) == ("agent_system", AGENT_SYSTEM_VERSION)
    assert text.startswith("You are the phone order-taker for Juniper Street Kitchen,")


def test_no_placeholders_left(text: str) -> None:
    assert "$" not in text


def test_every_tool_is_mentioned(text: str) -> None:
    missing = [name for name in TOOLS if name not in text]
    assert not missing, f"prompt never mentions: {missing}"


def keys_in(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_in(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_in(v)}
    return set()


def returned_keys(menu: Menu) -> set[str]:
    """Every key the tools return across a typical call."""
    session = Session.start(menu, "prompt-check")
    calls: list[tuple[str, dict[str, Any]]] = [
        ("search_menu", {"query": "cold coffee"}),
        ("add_item", {"item_id": "cold_coffee", "quantity": 1, "size_id": "large"}),
        ("update_item", {"line_id": 1, "quantity": 2}),
        ("set_customer", {"name": "Anil", "phone": "9000000001"}),
        ("get_order_summary", {}),
        ("get_readback", {}),
        ("confirm_order", {}),
        ("end_call", {"reason": "done"}),
    ]
    return {k for name, args in calls for k in keys_in(dispatch(session, TOOLS, name, args))}


def test_every_identifier_in_the_prompt_still_exists(text: str, menu: Menu) -> None:
    """snake_case words must be real tool names or keys the tools actually return."""
    identifiers = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))
    stale = sorted(identifiers - set(TOOLS) - returned_keys(menu))
    assert not stale, f"prompt refers to things the tools no longer have: {stale}"


def test_match_labels_in_the_prompt_are_real(text: str) -> None:
    for label in ("exact", "strong", "weak"):
        assert f'"{label}"' in text
        assert catalog.match_label({"exact": 100, "strong": 95, "weak": 10}[label]) == label


def test_missing_value_fails_loudly() -> None:
    with pytest.raises(KeyError, match="restaurant"):
        load_prompt("agent_system", AGENT_SYSTEM_VERSION)


def test_unknown_version_fails_loudly() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("agent_system", "v999", restaurant="x")


def test_greeting_names_the_restaurant() -> None:
    greeting = greeting_prompt("Juniper Street Kitchen")
    assert (
        greeting.text
        == "Hi, thanks for calling Juniper Street Kitchen. What would you like to order?"
    )
