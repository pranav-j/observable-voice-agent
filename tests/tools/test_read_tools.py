"""search_menu and get_order_summary."""

from typing import Any

import pytest

from voice_order.order import state
from voice_order.tools.base import Session, dispatch
from voice_order.tools.catalog import TOOLS


def call(session: Session, tool: str, /, **arguments: Any) -> dict[str, Any]:
    # Positional-only, so a tool argument called "name" goes into **arguments.
    return dispatch(session, TOOLS, tool, arguments)


# --- search_menu -------------------------------------------------------------------


def test_exact_match_with_sizes_and_modifiers(session: Session) -> None:
    result = call(session, "search_menu", query="cappuccino")
    top = result["matches"][0]
    assert (top["item_id"], top["match"], top["in_stock"]) == ("cappuccino", "exact", True)
    assert top["size_required"] is True
    assert top["sizes"][0] == {"size_id": "small", "name": "Small", "price": "160 rupees"}
    assert {"modifier_id": "oat_milk", "name": "Oat milk", "price": "40 rupees"} in top["modifiers"]
    assert "price" not in top  # sized items are priced per size
    assert "note" not in result


def test_unsized_item_has_a_single_price_and_free_modifiers(session: Session) -> None:
    top = call(session, "search_menu", query="paneer tikka")["matches"][0]
    assert top["price"] == "280 rupees"
    assert "sizes" not in top
    assert {"modifier_id": "less_spicy", "name": "Less spice", "price": "free"} in top["modifiers"]


def test_alias_and_stt_damage(session: Session) -> None:
    alias = call(session, "search_menu", query="iced coffee")["matches"][0]
    assert (alias["item_id"], alias["matched_on"], alias["match"]) == (
        "cold_coffee",
        "Iced Coffee",
        "exact",
    )
    garbled = call(session, "search_menu", query="pesaratu")["matches"][0]
    assert (garbled["item_id"], garbled["match"]) == ("pesarattu", "strong")


def test_out_of_stock_item_is_found_but_flagged(session: Session) -> None:
    top = call(session, "search_menu", query="mango lassi")["matches"][0]
    assert (top["item_id"], top["in_stock"]) == ("mango_lassi", False)


def test_ambiguous_query_tells_the_agent_to_ask(session: Session) -> None:
    result = call(session, "search_menu", query="biryani")
    assert "ask the caller which one" in result["note"]
    assert {m["item_id"] for m in result["matches"][:2]} == {"chicken_biryani", "veg_biryani"}


def test_unknown_item_says_probably_not_on_the_menu(session: Session) -> None:
    result = call(session, "search_menu", query="pizza")
    assert len(result["matches"]) == 5  # never empty-handed
    assert all(m["match"] == "weak" for m in result["matches"])
    assert "probably not on the menu" in result["note"]


@pytest.mark.parametrize("query", ["", "   ", "?!"])
def test_blank_query_is_invalid(session: Session, query: str) -> None:
    assert call(session, "search_menu", query=query)["error"] == "INVALID_ARGUMENTS"


# --- get_order_summary --------------------------------------------------------------


def test_summary_of_empty_order(session: Session) -> None:
    result = call(session, "get_order_summary")
    assert result["order"] == {
        "status": "draft",
        "lines": [],
        "total": "0 rupees",
        "customer": None,
        "readback_current": False,
    }
    assert "not the read-back" in result["note"]


def test_summary_lists_lines_prices_and_customer(session: Session) -> None:
    order = state.add_line(session.order, session.menu, "cold_coffee", 2, "large", ["oat_milk"])
    order = state.add_line(order, session.menu, "masala_dosa", 1)
    session.order = state.set_customer(order, "Anil", "9000000001")
    view = call(session, "get_order_summary")["order"]
    assert view["lines"][0] == {
        "line_id": 1,
        "description": "Two large Cold Coffee with oat milk",
        "item_id": "cold_coffee",
        "size_id": "large",
        "modifier_ids": ["oat_milk"],
        "quantity": 2,
        "line_total": "560 rupees",
    }
    assert view["total"] == "700 rupees"
    assert view["customer"] == {"name": "Anil", "phone": "9000000001"}


def test_summary_tracks_whether_the_readback_is_current(session: Session) -> None:
    session.order = state.mark_readback(state.add_line(session.order, session.menu, "affogato", 1))
    assert call(session, "get_order_summary")["order"]["readback_current"] is True
    session.order = state.add_line(session.order, session.menu, "affogato", 1)
    assert call(session, "get_order_summary")["order"]["readback_current"] is False


def test_reading_does_not_change_the_order(session: Session) -> None:
    before = session.order
    call(session, "search_menu", query="dosa")
    call(session, "get_order_summary")
    assert session.order is before
