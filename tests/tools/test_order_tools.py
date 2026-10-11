"""add_item, update_item, remove_item, set_customer: success paths and every error path."""

from typing import Any

import pytest

from voice_order.order import state
from voice_order.tools.base import Session, dispatch
from voice_order.tools.catalog import TOOLS


def call(session: Session, tool: str, /, **arguments: Any) -> dict[str, Any]:
    # Positional-only, so a tool argument called "name" goes into **arguments.
    return dispatch(session, TOOLS, tool, arguments)


@pytest.fixture
def with_coffee(session: Session) -> Session:
    """Line 1: one large cold coffee with oat milk."""
    session.order = state.add_line(
        session.order, session.menu, "cold_coffee", 1, "large", ["oat_milk"]
    )
    return session


# --- success paths -------------------------------------------------------------------


def test_add_item_updates_the_session(session: Session) -> None:
    result = call(
        session, "add_item", item_id="cappuccino", quantity=2, size_id="small", modifier_ids=[]
    )
    assert result["ok"] is True
    (line,) = result["order"]["lines"]
    assert (line["line_id"], line["description"]) == (1, "Two small Cappuccino")
    assert result["order"]["total"] == "320 rupees"
    assert session.order.lines[0].item_id == "cappuccino"


def test_add_item_with_only_required_arguments(session: Session) -> None:
    result = call(session, "add_item", item_id="masala_dosa", quantity="1")
    assert result["order"]["lines"][0]["description"] == "One Masala Dosa"


def test_update_item_changes_only_what_is_given(with_coffee: Session) -> None:
    result = call(with_coffee, "update_item", line_id=1, quantity=3)
    assert result["order"]["lines"][0]["description"] == "Three large Cold Coffee with oat milk"


def test_update_item_can_clear_modifiers(with_coffee: Session) -> None:
    result = call(with_coffee, "update_item", line_id=1, modifier_ids=[], size_id="small")
    assert result["order"]["lines"][0]["description"] == "One small Cold Coffee"


def test_update_item_accepts_explicit_nulls(with_coffee: Session) -> None:
    result = call(
        with_coffee, "update_item", line_id=1, quantity=2, size_id=None, modifier_ids=None
    )
    assert result["order"]["lines"][0]["description"] == "Two large Cold Coffee with oat milk"


def test_remove_item(with_coffee: Session) -> None:
    result = call(with_coffee, "remove_item", line_id=1)
    assert result["order"]["lines"] == []
    assert with_coffee.order.lines == []


def test_set_customer_normalizes_and_groups_the_phone(session: Session) -> None:
    result = call(session, "set_customer", name=" Anil ", phone="+91 90000 00001")
    assert result["order"]["customer"] == {"name": "Anil", "phone": "9000000001"}
    assert result["read_phone_back_as"] == "90000 00001"


def test_a_name_fix_doesnt_ask_for_the_number_again(session: Session) -> None:
    call(session, "set_customer", name="Garev", phone="98765 30102")
    fixed = call(session, "set_customer", name="Gaurav", phone="98765 30102")
    assert "read_phone_back_as" not in fixed
    assert "spell it letter by letter" in fixed["note"]
    new_number = call(session, "set_customer", name="Gaurav", phone="98765 30103")
    assert new_number["read_phone_back_as"] == "98765 30103"
    assert "note" not in new_number


def test_a_name_fix_after_the_readback_keeps_both_notes(session: Session) -> None:
    call(session, "add_item", item_id="masala_dosa", quantity=1)
    call(session, "set_customer", name="Garev", phone="98765 30102")
    call(session, "get_readback")
    fixed = call(session, "set_customer", name="Gaurav", phone="98765 30102")
    assert "spell it" in fixed["note"]
    assert "get_readback again" in fixed["note"]


def test_setting_the_same_customer_again_suggests_spelling(session: Session) -> None:
    first = call(session, "set_customer", name="Nick Hill", phone="98765 69314")
    assert "note" not in first
    again = call(session, "set_customer", name="Nick Hill", phone="98765 69314")
    assert "spell it letter by letter" in again["note"]


def test_a_number_given_in_two_parts_is_joined(session: Session) -> None:
    # The caller paused after five digits and the pause ended their turn.
    first = call(session, "set_customer", name="Priya", phone="nine zero zero zero zero")
    assert first["error"] == "PHONE_INCOMPLETE"
    assert first["digits_so_far"] == 5
    assert session.order.customer is None
    second = call(session, "set_customer", name="Priya", phone="zero zero zero zero two")
    assert second["order"]["customer"] == {"name": "Priya", "phone": "9000000002"}
    assert session.phone_digits == ""


def test_a_number_in_three_parts_with_a_prefix(session: Session) -> None:
    assert call(session, "set_customer", name="Anil", phone="+91 98")["ok"] is False
    assert call(session, "set_customer", name="Anil", phone="765")["ok"] is False
    result = call(session, "set_customer", name="Anil", phone="43210")
    assert result["order"]["customer"]["phone"] == "9876543210"


def test_a_whole_number_replaces_a_held_part(session: Session) -> None:
    call(session, "set_customer", name="Priya", phone="9 0 0")
    result = call(session, "set_customer", name="Priya", phone="98765 43210")
    assert result["order"]["customer"]["phone"] == "9876543210"
    assert session.phone_digits == ""


def test_too_many_digits_drops_the_held_part(session: Session) -> None:
    call(session, "set_customer", name="Priya", phone="90000")
    result = call(session, "set_customer", name="Priya", phone="900000000")
    assert result["error"] == "INVALID_PHONE"
    assert session.phone_digits == ""


# --- every error path ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "arguments", "code"),
    [
        ("add_item", {"item_id": "pizza", "quantity": 1}, "UNKNOWN_ITEM"),
        ("add_item", {"item_id": "cappuccino", "quantity": 1}, "SIZE_REQUIRED"),
        ("add_item", {"item_id": "cappuccino", "quantity": 1, "size_id": "venti"}, "INVALID_SIZE"),
        ("add_item", {"item_id": "masala_dosa", "quantity": 1, "size_id": "large"}, "INVALID_SIZE"),
        (
            "add_item",
            {"item_id": "masala_dosa", "quantity": 1, "modifier_ids": ["oat_milk"]},
            "INVALID_MODIFIER",
        ),
        ("add_item", {"item_id": "masala_dosa", "quantity": 0}, "INVALID_QUANTITY"),
        ("add_item", {"item_id": "masala_dosa", "quantity": 25}, "INVALID_QUANTITY"),
        ("add_item", {"item_id": "masala_dosa"}, "INVALID_ARGUMENTS"),
        (
            "add_item",
            {"item_id": "cappuccino", "quantity": 1, "size": "small"},
            "INVALID_ARGUMENTS",
        ),
        ("update_item", {"line_id": 9, "quantity": 2}, "UNKNOWN_LINE"),
        ("update_item", {"line_id": 1, "quantity": 21}, "INVALID_QUANTITY"),
        ("update_item", {"line_id": 1, "size_id": "venti"}, "INVALID_SIZE"),
        ("update_item", {"line_id": 1, "modifier_ids": ["cheese"]}, "INVALID_MODIFIER"),
        ("remove_item", {"line_id": 9}, "UNKNOWN_LINE"),
        ("set_customer", {"name": "  ", "phone": "9000000001"}, "INVALID_NAME"),
        ("set_customer", {"name": "Anil", "phone": "0123456789"}, "INVALID_PHONE"),
        ("set_customer", {"name": "Anil", "phone": "my number"}, "INVALID_PHONE"),
        ("set_customer", {"name": "Anil", "phone": "12345"}, "PHONE_INCOMPLETE"),
        ("set_customer", {"name": "Anil"}, "INVALID_ARGUMENTS"),
    ],
)
def test_errors_are_reported_and_leave_the_order_unchanged(
    with_coffee: Session, tool: str, arguments: dict[str, Any], code: str
) -> None:
    before = with_coffee.order
    result = call(with_coffee, tool, **arguments)
    assert (result["ok"], result["error"]) == (False, code)
    assert result["message"]
    assert with_coffee.order is before


def test_out_of_stock_offers_named_alternatives(session: Session) -> None:
    result = call(session, "add_item", item_id="mango_lassi", quantity=1, size_id="regular")
    assert result["error"] == "OUT_OF_STOCK"
    assert {"item_id": "sweet_lassi", "name": "Sweet Lassi"} in result["alternatives"]


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("add_item", {"item_id": "affogato", "quantity": 1}),
        ("update_item", {"line_id": 1, "quantity": 2}),
        ("remove_item", {"line_id": 1}),
        ("set_customer", {"name": "Ravi", "phone": "9000000002"}),
    ],
)
def test_changes_after_confirmation_are_refused(
    with_coffee: Session, tool: str, arguments: dict[str, Any]
) -> None:
    order = state.set_customer(with_coffee.order, "Anil", "9000000001")
    with_coffee.order = state.confirm(state.mark_readback(order))
    assert call(with_coffee, tool, **arguments)["error"] == "ORDER_CLOSED"


# --- stale read-back warning ---------------------------------------------------------------


def test_change_after_readback_warns(with_coffee: Session) -> None:
    with_coffee.order = state.mark_readback(with_coffee.order)
    result = call(with_coffee, "update_item", line_id=1, size_id="small")
    assert "Call get_readback again" in result["note"]
    assert result["order"]["readback_current"] is False


def test_no_warning_without_a_readback(with_coffee: Session) -> None:
    assert "note" not in call(with_coffee, "update_item", line_id=1, size_id="small")


def test_no_warning_when_nothing_changed(with_coffee: Session) -> None:
    with_coffee.order = state.mark_readback(with_coffee.order)
    result = call(with_coffee, "update_item", line_id=1, quantity=1)
    assert "note" not in result
    assert result["order"]["readback_current"] is True


def test_swapping_the_item_via_update_explains_how(with_coffee: Session) -> None:
    before = with_coffee.order
    result = call(with_coffee, "update_item", line_id=1, item_id="cold_brew")
    assert result["error"] == "INVALID_ARGUMENTS"
    assert "call remove_item for this line, then add_item" in result["message"]
    assert with_coffee.order is before


def test_update_item_schema_does_not_offer_item_id() -> None:
    assert "item_id" not in TOOLS["update_item"].parameters_schema()["properties"]
