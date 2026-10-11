"""Order state machine: every transition, every error path, and the confirm rule."""

from collections.abc import Callable

import pytest

from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.order.errors import ErrorCode, OrderError
from voice_order.order.models import Order

PHONE = "9000000001"


def expect_error(code: ErrorCode, fn: Callable[[], object]) -> OrderError:
    with pytest.raises(OrderError) as info:
        fn()
    assert info.value.code == code
    return info.value


@pytest.fixture
def empty() -> Order:
    return state.new_order("test-session")


@pytest.fixture
def ready(empty: Order, menu: Menu) -> Order:
    """An order with one dosa and a customer, but no read-back yet."""
    order = state.add_line(empty, menu, "masala_dosa", 2)
    return state.set_customer(order, "Anil", PHONE)


# --- add_line ----------------------------------------------------------------


def test_new_order_is_an_empty_draft(empty: Order) -> None:
    assert (empty.status, empty.lines, empty.customer) == ("draft", [], None)
    assert (empty.mutation_seq, empty.readback_seq) == (0, None)


def test_add_line(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "cold_coffee", 1, size_id="large")
    (line,) = order.lines
    assert (line.line_id, line.item_id, line.size_id, line.quantity) == (
        1,
        "cold_coffee",
        "large",
        1,
    )
    assert order.mutation_seq == 1


def test_operations_never_change_the_original(empty: Order, menu: Menu) -> None:
    state.add_line(empty, menu, "masala_dosa", 1)
    assert empty.lines == []
    assert empty.mutation_seq == 0


def test_modifiers_are_sorted_and_deduplicated(empty: Order, menu: Menu) -> None:
    order = state.add_line(
        empty, menu, "cappuccino", 1, "small", ["oat_milk", "extra_shot", "oat_milk"]
    )
    assert order.lines[0].modifier_ids == ["extra_shot", "oat_milk"]


def test_same_item_merges_into_one_line(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "masala_dosa", 2)
    order = state.add_line(order, menu, "masala_dosa", 1)
    assert [(x.line_id, x.quantity) for x in order.lines] == [(1, 3)]
    assert order.mutation_seq == 2


def test_different_modifiers_stay_separate_lines(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "masala_dosa", 1)
    order = state.add_line(order, menu, "masala_dosa", 1, modifier_ids=["cheese"])
    assert [x.modifier_ids for x in order.lines] == [[], ["cheese"]]


def test_line_ids_are_never_reused(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "masala_dosa", 1)
    order = state.add_line(order, menu, "pesarattu", 1)
    order = state.remove_line(order, 2)
    order = state.add_line(order, menu, "affogato", 1)
    assert [x.line_id for x in order.lines] == [1, 3]


def test_unknown_item(empty: Order, menu: Menu) -> None:
    expect_error(ErrorCode.UNKNOWN_ITEM, lambda: state.add_line(empty, menu, "pizza", 1))


def test_out_of_stock_offers_in_stock_alternatives(empty: Order, menu: Menu) -> None:
    err = expect_error(
        ErrorCode.OUT_OF_STOCK, lambda: state.add_line(empty, menu, "mango_lassi", 1, "regular")
    )
    assert err.alternatives
    assert "mango_lassi" not in err.alternatives
    for alt_id in err.alternatives:
        alt = menu.item(alt_id)
        assert alt is not None
        assert alt.in_stock
        assert alt.category == "Cold Drinks"


def test_size_required(empty: Order, menu: Menu) -> None:
    err = expect_error(
        ErrorCode.SIZE_REQUIRED, lambda: state.add_line(empty, menu, "cappuccino", 1)
    )
    assert "small, medium, large" in err.message


def test_invalid_size(empty: Order, menu: Menu) -> None:
    expect_error(
        ErrorCode.INVALID_SIZE, lambda: state.add_line(empty, menu, "cappuccino", 1, "venti")
    )


def test_size_on_item_without_sizes(empty: Order, menu: Menu) -> None:
    expect_error(
        ErrorCode.INVALID_SIZE, lambda: state.add_line(empty, menu, "masala_dosa", 1, "large")
    )


def test_invalid_modifier(empty: Order, menu: Menu) -> None:
    err = expect_error(
        ErrorCode.INVALID_MODIFIER,
        lambda: state.add_line(empty, menu, "masala_dosa", 1, modifier_ids=["oat_milk"]),
    )
    assert "cheese, extra_butter" in err.message


@pytest.mark.parametrize("quantity", [0, -1, 21])
def test_invalid_quantity(empty: Order, menu: Menu, quantity: int) -> None:
    expect_error(
        ErrorCode.INVALID_QUANTITY, lambda: state.add_line(empty, menu, "masala_dosa", quantity)
    )


def test_merge_cannot_exceed_max_quantity(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "masala_dosa", 15)
    expect_error(ErrorCode.INVALID_QUANTITY, lambda: state.add_line(order, menu, "masala_dosa", 6))


# --- update_line and remove_line ----------------------------------------------


def test_update_quantity_size_and_modifiers(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "cold_coffee", 1, "large", ["oat_milk"])
    order = state.update_line(order, menu, 1, quantity=2, size_id="medium", modifier_ids=[])
    (line,) = order.lines
    assert (line.quantity, line.size_id, line.modifier_ids) == (2, "medium", [])
    assert order.mutation_seq == 2


def test_update_leaves_unspecified_fields_alone(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "cold_coffee", 1, "large", ["oat_milk"])
    order = state.update_line(order, menu, 1, quantity=3)
    (line,) = order.lines
    assert (line.quantity, line.size_id, line.modifier_ids) == (3, "large", ["oat_milk"])


def test_update_with_no_change_keeps_the_readback_valid(ready: Order, menu: Menu) -> None:
    order = state.mark_readback(ready)
    assert state.update_line(order, menu, 1, quantity=2) is order


def test_update_that_matches_another_line_merges(empty: Order, menu: Menu) -> None:
    order = state.add_line(empty, menu, "cold_coffee", 1, "small")
    order = state.add_line(order, menu, "cold_coffee", 2, "medium")
    order = state.update_line(order, menu, 1, size_id="medium")
    assert [(x.line_id, x.size_id, x.quantity) for x in order.lines] == [(2, "medium", 3)]


@pytest.mark.parametrize(
    ("code", "kwargs"),
    [
        (ErrorCode.INVALID_QUANTITY, {"quantity": 0}),
        (ErrorCode.INVALID_SIZE, {"size_id": "huge"}),
        (ErrorCode.INVALID_MODIFIER, {"modifier_ids": ["cheese"]}),
    ],
)
def test_update_validates_like_add(
    empty: Order, menu: Menu, code: ErrorCode, kwargs: dict[str, object]
) -> None:
    order = state.add_line(empty, menu, "cold_coffee", 1, "small")
    expect_error(code, lambda: state.update_line(order, menu, 1, **kwargs))  # type: ignore[arg-type]


def test_update_unknown_line(ready: Order, menu: Menu) -> None:
    err = expect_error(
        ErrorCode.UNKNOWN_LINE, lambda: state.update_line(ready, menu, 9, quantity=1)
    )
    assert "Current lines: 1" in err.message


def test_remove_line(ready: Order) -> None:
    order = state.remove_line(ready, 1)
    assert order.lines == []
    assert order.mutation_seq == ready.mutation_seq + 1


def test_remove_unknown_line(ready: Order) -> None:
    expect_error(ErrorCode.UNKNOWN_LINE, lambda: state.remove_line(ready, 9))


# --- set_customer ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "9000000001",
        "90000 00001",
        "900-000-0001",
        "+91 90000 00001",
        "91 9000000001",
        "09000000001",
    ],
)
def test_phone_is_normalized_to_ten_digits(empty: Order, raw: str) -> None:
    order = state.set_customer(empty, "  Anil   Kumar ", raw)
    assert order.customer is not None
    assert (order.customer.name, order.customer.phone) == ("Anil Kumar", PHONE)


@pytest.mark.parametrize(
    "raw", ["900000001", "190000000001", "0091 90000 00001", "phone", "", "19000000001"]
)
def test_invalid_phone(empty: Order, raw: str) -> None:
    expect_error(ErrorCode.INVALID_PHONE, lambda: state.set_customer(empty, "Anil", raw))


def test_blank_name(empty: Order) -> None:
    expect_error(ErrorCode.INVALID_NAME, lambda: state.set_customer(empty, "   ", PHONE))


def test_setting_the_same_customer_is_not_a_change(ready: Order) -> None:
    assert state.set_customer(ready, "Anil", "+91 90000 00001") is ready


def test_changing_the_customer_bumps_the_sequence(ready: Order) -> None:
    order = state.set_customer(ready, "Anil", "9000000002")
    assert order.mutation_seq == ready.mutation_seq + 1


# --- read-back and the confirm rule ------------------------------------------------


def test_confirm_after_readback(ready: Order) -> None:
    order = state.confirm(state.mark_readback(ready))
    assert order.status == "confirmed"


def test_mark_readback_records_the_current_sequence(ready: Order) -> None:
    order = state.mark_readback(ready)
    assert order.readback_seq == ready.mutation_seq
    assert order.mutation_seq == ready.mutation_seq  # fetching the read-back is not a change


def test_confirm_without_readback(ready: Order) -> None:
    err = expect_error(ErrorCode.READBACK_REQUIRED, lambda: state.confirm(ready))
    assert "has not been given" in err.message


@pytest.mark.parametrize(
    "change",
    [
        lambda o, m: state.add_line(o, m, "affogato", 1),
        lambda o, m: state.update_line(o, m, 1, quantity=3),
        lambda o, m: state.remove_line(o, 1),
        lambda o, m: state.set_customer(o, "Anil", "9000000002"),
    ],
    ids=["add", "update", "remove", "customer"],
)
def test_any_change_after_readback_blocks_confirm(
    ready: Order, menu: Menu, change: Callable[[Order, Menu], Order]
) -> None:
    order = change(state.mark_readback(ready), menu)
    err = expect_error(ErrorCode.READBACK_REQUIRED, lambda: state.confirm(order))
    assert "changed after the last read-back" in err.message or "no items" in err.message


def test_a_fresh_readback_unblocks_confirm(ready: Order, menu: Menu) -> None:
    order = state.add_line(state.mark_readback(ready), menu, "affogato", 1)
    order = state.confirm(state.mark_readback(order))
    assert order.status == "confirmed"


def test_confirm_needs_items(empty: Order) -> None:
    order = state.mark_readback(state.set_customer(empty, "Anil", PHONE))
    err = expect_error(ErrorCode.READBACK_REQUIRED, lambda: state.confirm(order))
    assert "no items" in err.message


def test_confirm_needs_a_customer(empty: Order, menu: Menu) -> None:
    order = state.mark_readback(state.add_line(empty, menu, "masala_dosa", 1))
    err = expect_error(ErrorCode.READBACK_REQUIRED, lambda: state.confirm(order))
    assert "name and phone" in err.message


# --- closing the order --------------------------------------------------------------


@pytest.fixture
def confirmed(ready: Order) -> Order:
    return state.confirm(state.mark_readback(ready))


@pytest.mark.parametrize(
    "action",
    [
        lambda o, m: state.add_line(o, m, "affogato", 1),
        lambda o, m: state.update_line(o, m, 1, quantity=3),
        lambda o, m: state.remove_line(o, 1),
        lambda o, m: state.set_customer(o, "Ravi", "9000000002"),
        lambda o, m: state.mark_readback(o),
        lambda o, m: state.confirm(o),
    ],
    ids=["add", "update", "remove", "customer", "readback", "confirm"],
)
def test_closed_orders_reject_changes(
    confirmed: Order, menu: Menu, action: Callable[[Order, Menu], Order]
) -> None:
    expect_error(ErrorCode.ORDER_CLOSED, lambda: action(confirmed, menu))


def test_escalate_and_abandon_close_a_draft(ready: Order) -> None:
    assert state.escalate(ready).status == "escalated"
    assert state.abandon(ready).status == "abandoned"


def test_escalate_and_abandon_keep_a_confirmed_order(confirmed: Order) -> None:
    assert state.escalate(confirmed).status == "confirmed"
    assert state.abandon(confirmed).status == "confirmed"
