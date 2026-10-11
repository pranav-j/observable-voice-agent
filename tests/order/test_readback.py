"""The read-back text, generated in code from the order and menu."""

import pytest

from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.order.errors import ErrorCode, OrderError
from voice_order.order.models import MAX_QUANTITY, Order
from voice_order.order.pricing import price_order
from voice_order.order.readback import (
    NUMBER_WORDS,
    build_readback,
    group_phone,
    join_words,
    spoken_inr,
    spoken_name,
)


def make_order(menu: Menu, *lines: tuple[str, int, str | None, list[str]]) -> Order:
    order = state.new_order("s")
    for item_id, qty, size_id, mods in lines:
        order = state.add_line(order, menu, item_id, qty, size_id, mods)
    return state.set_customer(order, "Anil", "9000000001")


def readback_text(menu: Menu, *lines: tuple[str, int, str | None, list[str]]) -> str:
    return build_readback(make_order(menu, *lines), menu).text


def test_full_readback(menu: Menu) -> None:
    text = readback_text(
        menu,
        ("masala_dosa", 2, None, ["cheese"]),
        ("cold_coffee", 1, "large", ["oat_milk", "extra_shot"]),
        ("butter_naan", 3, None, ["garlic"]),
        ("paneer_tikka", 1, None, ["less_spicy"]),
    )
    assert text == (
        "Let me read that back. "
        "Two Masala Dosa with cheese. "
        "One large Cold Coffee with oat milk and extra shot. "
        "Three Butter Naan with garlic. "
        "One Paneer Tikka with less spice. "
        "Your total is 1,160 rupees. "
        "The order is for Anil, phone number 90000 00001. "
        "Is that correct?"
    )


def test_bracketed_notes_are_not_spoken(menu: Menu) -> None:
    assert "Four Veg Samosa." in readback_text(menu, ("veg_samosa", 4, None, []))


def test_three_modifiers(menu: Menu) -> None:
    text = readback_text(
        menu, ("cappuccino", 1, "small", ["hazelnut_syrup", "extra_shot", "oat_milk"])
    )
    assert "One small Cappuccino with oat milk, extra shot and hazelnut syrup." in text


def test_largest_quantity_has_a_word(menu: Menu) -> None:
    assert "Twenty Affogato." in readback_text(menu, ("affogato", MAX_QUANTITY, None, []))


def test_number_words_cover_every_quantity() -> None:
    assert len(NUMBER_WORDS) == MAX_QUANTITY + 1


def test_total_and_version_come_from_the_order(menu: Menu) -> None:
    order = make_order(menu, ("chicken_biryani", 2, "full", ["extra_raita"]))
    readback = build_readback(order, menu)
    assert readback.total_paise == price_order(order, menu).total_paise == 74000
    assert readback.mutation_seq == order.mutation_seq
    assert "Your total is 740 rupees." in readback.text


def test_needs_items(menu: Menu) -> None:
    order = state.set_customer(state.new_order("s"), "Anil", "9000000001")
    with pytest.raises(OrderError) as info:
        build_readback(order, menu)
    assert info.value.code == ErrorCode.ORDER_INCOMPLETE
    assert info.value.message == "Before the read-back, collect at least one item."


def test_needs_customer(menu: Menu) -> None:
    order = state.add_line(state.new_order("s"), menu, "affogato", 1)
    with pytest.raises(OrderError) as info:
        build_readback(order, menu)
    assert info.value.code == ErrorCode.ORDER_INCOMPLETE
    assert "name and phone number" in info.value.message


def test_reports_everything_missing(menu: Menu) -> None:
    with pytest.raises(OrderError) as info:
        build_readback(state.new_order("s"), menu)
    assert info.value.message == (
        "Before the read-back, collect at least one item and the customer's name and phone number."
    )


@pytest.mark.parametrize(
    ("paise", "spoken"),
    [
        (116000, "1,160 rupees"),
        (12500000, "1,25,000 rupees"),
        (1250, "12 rupees 50 paise"),
        (50, "50 paise"),
        (100, "1 rupee"),
        (101, "1 rupee 1 paisa"),
        (0, "0 rupees"),
    ],
)
def test_spoken_inr(paise: int, spoken: str) -> None:
    assert spoken_inr(paise) == spoken


def test_helpers() -> None:
    assert group_phone("9876543210") == "98765 43210"
    assert spoken_name("Gulab Jamun (2 pcs)") == "Gulab Jamun"
    assert join_words(["a"]) == "a"
    assert join_words(["a", "b"]) == "a and b"
    assert join_words(["a", "b", "c"]) == "a, b and c"
