"""Scenario files load, follow the schema, and only expect orders the menu can produce."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from evals.scenario import SCENARIO_DIR, Scenario, load_scenario, load_scenarios, menu_problems
from pydantic import ValidationError

from voice_order.menu.models import Menu

SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))


def minimal(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "example",
        "description": "d",
        "persona": {"name": "Anil", "style": "brisk"},
        "goal": "g",
        "customer": {"name": "Anil", "phone": "9000000001"},
        "expect": {
            "status": "confirmed",
            "order": {"items": [{"item": "masala_dosa", "quantity": 2}]},
        },
    }
    return base | overrides


# --- the real scenario files ------------------------------------------------------------


def test_there_are_scenarios() -> None:
    assert SCENARIO_FILES


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_file_is_valid_and_matches_the_menu(path: Path, menu: Menu) -> None:
    scenario = load_scenario(path)
    assert menu_problems(scenario, menu) == []


CATEGORIES = {
    "happy_path",
    "correction",
    "barge_in",
    "hesitation",
    "ambiguity",
    "out_of_stock",
    "phone_name",
    "noise_accent",
    "injection",
    "human",
}


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_first_tag_is_a_known_category(path: Path) -> None:
    tags = load_scenario(path).tags
    assert tags, "every scenario needs a category tag"
    assert tags[0] in CATEGORIES, f"first tag {tags[0]!r} is not one of {sorted(CATEGORIES)}"


def test_customer_phones_are_unique() -> None:
    phones = [load_scenario(p).customer.phone for p in SCENARIO_FILES]
    assert len(phones) == len(set(phones))


def test_load_scenarios_filters_by_glob() -> None:
    happy = load_scenarios("happy_path_*")
    assert happy
    assert all(s.id.startswith("happy_path_") for s in happy)
    assert [s.id for s in load_scenarios("happy_path_single_coffee")] == [
        "happy_path_single_coffee"
    ]
    assert len(load_scenarios()) == len(SCENARIO_FILES) > len(happy)


# --- schema rules -------------------------------------------------------------------------


def test_minimal_scenario_gets_defaults() -> None:
    s = Scenario.model_validate(minimal())
    assert (s.runs, s.max_turns, s.behaviors, s.tags) == (1, 30, [], [])


@pytest.mark.parametrize(
    "overrides",
    [
        {"extra_field": 1},
        {"persona": {"name": "A", "style": "grumpy"}},
        {"customer": {"name": "A", "phone": "9876543210"}},  # a real-looking number
        {"runs": 0},
        {"behaviors": [{"trigger": {}, "action": "interrupt", "after_ms": 1, "say": "x"}]},
        {
            "behaviors": [
                {
                    "trigger": {"phase": "readback", "turn": 2},
                    "action": "interrupt",
                    "after_ms": 1,
                    "say": "x",
                }
            ]
        },
        {"behaviors": [{"trigger": {"phase": "readback"}, "action": "interrupt", "after_ms": 1}]},
        {"behaviors": [{"trigger": {"turn": 2}, "action": "pause_mid_utterance"}]},
        {"expect": {"status": "shipped"}},
        {"expect": {"status": "confirmed", "order": {"items": [{"item": "x", "quantity": 0}]}}},
    ],
    ids=[
        "unknown-field",
        "unknown-style",
        "real-phone",
        "zero-runs",
        "empty-trigger",
        "two-triggers",
        "interrupt-without-say",
        "pause-without-ms",
        "bad-status",
        "zero-quantity",
    ],
)
def test_invalid_scenarios_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate(minimal(**overrides))


def test_id_must_match_file_name(tmp_path: Path) -> None:
    path = tmp_path / "other_name.yaml"
    path.write_text(yaml.safe_dump(minimal()))
    with pytest.raises(ValueError, match="must match the file name"):
        load_scenario(path)


# --- menu consistency ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "problem"),
    [
        ({"item": "pizza"}, "unknown item 'pizza'"),
        ({"item": "cold_coffee"}, "cold_coffee: size None not in"),
        ({"item": "cold_coffee", "size": "venti"}, "cold_coffee: size 'venti' not in"),
        ({"item": "masala_dosa", "size": "large"}, "masala_dosa: has no sizes"),
        ({"item": "masala_dosa", "modifiers": ["oat_milk"]}, "unknown modifier 'oat_milk'"),
        ({"item": "mutton_rogan_josh"}, "out of stock but expected in a confirmed order"),
    ],
)
def test_menu_problems_are_found(menu: Menu, item: dict[str, Any], problem: str) -> None:
    scenario = Scenario.model_validate(
        minimal(expect={"status": "confirmed", "order": {"items": [item]}})
    )
    problems = menu_problems(scenario, menu)
    assert any(problem in p for p in problems), problems


def test_unscored_order_has_no_menu_problems(menu: Menu) -> None:
    scenario = Scenario.model_validate(minimal(expect={"status": "escalated"}))
    assert menu_problems(scenario, menu) == []
