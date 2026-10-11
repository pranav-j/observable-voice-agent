"""Fuzzy search ranking on the seed menu."""

import pytest

from voice_order.menu.loader import load_menu
from voice_order.menu.models import Menu
from voice_order.menu.search import search


@pytest.fixture(scope="module")
def menu() -> Menu:
    return load_menu()


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # exact names, any case or spacing
        ("Masala Dosa", "masala_dosa"),
        ("  paneer   TIKKA ", "paneer_tikka"),
        ("paneer tikka roll", "paneer_tikka_roll"),
        # aliases
        ("iced coffee", "cold_coffee"),
        ("nimbu soda", "fresh_lime_soda"),
        ("black coffee", "americano"),
        ("naan", "butter_naan"),
        # the kind of damage STT does to unusual names
        ("pesaratu", "pesarattu"),
        ("bisi bele bat", "bisi_bele_bath"),
        ("afogato", "affogato"),
        ("cappucino", "cappuccino"),
        # partial names
        ("mysore dosa", "mysore_masala_dosa"),
    ],
)
def test_top_hit(menu: Menu, query: str, expected: str) -> None:
    hit = search(menu, query)[0]
    assert hit.item.id == expected
    assert hit.score >= 90


@pytest.mark.parametrize(
    ("query", "exact", "runner_up"),
    [
        ("paneer tikka", "paneer_tikka", "paneer_tikka_roll"),
        ("masala dosa", "masala_dosa", "mysore_masala_dosa"),
        ("chai", "masala_chai", "chai_latte"),
    ],
)
def test_exact_match_beats_its_confusable(
    menu: Menu, query: str, exact: str, runner_up: str
) -> None:
    first, second = search(menu, query)[:2]
    assert (first.item.id, second.item.id) == (exact, runner_up)
    assert first.score == 100
    assert second.score < 100


@pytest.mark.parametrize(
    ("query", "tied"),
    [
        ("biryani", {"chicken_biryani", "veg_biryani"}),
        ("tikka roll", {"paneer_tikka_roll", "chicken_tikka_roll"}),
    ],
)
def test_ambiguous_queries_tie(menu: Menu, query: str, tied: set[str]) -> None:
    hits = search(menu, query)
    top = [h for h in hits if h.score == hits[0].score]
    assert {h.item.id for h in top} == tied


def test_out_of_stock_items_are_still_found(menu: Menu) -> None:
    hit = search(menu, "cheesecake")[0]
    assert hit.item.id == "blueberry_cheesecake"
    assert not hit.item.in_stock


def test_matched_reports_the_alias(menu: Menu) -> None:
    hit = search(menu, "iced coffee")[0]
    assert hit.matched == "Iced Coffee"
    assert hit.item.name == "Cold Coffee"


@pytest.mark.parametrize(
    "query",
    [
        "pizza",
        "xyzzy",
        "banana split",
        # menu names hidden inside other words must not match ("p-latte-r", "chai-ned")
        "sushi platter",
        "chained",
    ],
)
def test_unknown_items_still_return_hits_with_low_scores(menu: Menu, query: str) -> None:
    hits = search(menu, query)
    assert len(hits) == 5
    assert hits[0].score < 80


def test_results_are_sorted_and_limited(menu: Menu) -> None:
    hits = search(menu, "coffee", limit=3)
    assert len(hits) == 3
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)


def test_results_are_deterministic(menu: Menu) -> None:
    assert search(menu, "coffee") == search(menu, "coffee")


@pytest.mark.parametrize("query", ["", "   ", "?!"])
def test_blank_query_rejected(menu: Menu, query: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        search(menu, query)


def test_limit_must_be_positive(menu: Menu) -> None:
    with pytest.raises(ValueError, match="limit"):
        search(menu, "dosa", limit=0)
