"""Prices come only from the menu, computed at call time."""

import json

import pytest

from voice_order.menu.loader import DEFAULT_MENU_PATH
from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.order.errors import ErrorCode, OrderError
from voice_order.order.models import Order, OrderLine
from voice_order.order.pricing import format_inr, price_order

# (item_id, quantity, size_id, modifier_ids)
SAMPLE = [
    ("masala_dosa", 2, None, ["cheese"]),
    ("cold_coffee", 1, "large", ["oat_milk", "extra_shot"]),
    ("butter_naan", 3, None, ["garlic"]),
    ("paneer_tikka", 1, None, ["less_spicy"]),  # free modifier
]


@pytest.fixture
def sample(menu: Menu) -> Order:
    order = state.new_order("s")
    for item_id, qty, size_id, mods in SAMPLE:
        order = state.add_line(order, menu, item_id, qty, size_id, mods)
    return order


def test_orders_carry_no_prices() -> None:
    for model in (Order, OrderLine):
        assert not [f for f in model.model_fields if "price" in f or "total" in f]


def test_total_matches_an_independent_calculation_from_the_raw_file(
    sample: Order, menu: Menu
) -> None:
    raw = {i["id"]: i for i in json.loads(DEFAULT_MENU_PATH.read_text())["items"]}
    expected = 0
    for item_id, qty, size_id, mods in SAMPLE:
        item = raw[item_id]
        unit = (
            next(s["price_paise"] for s in item["sizes"] if s["id"] == size_id)
            if size_id
            else item["base_price_paise"]
        )
        unit += sum(m["price_paise"] for m in item.get("modifiers", []) if m["id"] in mods)
        expected += unit * qty
    # (140+30)*2 + (240+40+50) + (60+10)*3 + 280 = 340 + 330 + 210 + 280 = ₹1,160
    assert expected == 116000
    assert price_order(sample, menu).total_paise == expected


def test_line_breakdown(sample: Order, menu: Menu) -> None:
    coffee = price_order(sample, menu).lines[1]
    assert (coffee.name, coffee.size_name) == ("Cold Coffee", "Large")
    assert coffee.modifier_names == ["Oat milk", "Extra shot"]  # menu order, not id order
    assert (coffee.unit_price_paise, coffee.quantity, coffee.line_total_paise) == (33000, 1, 33000)


def test_repricing_the_menu_reprices_the_same_order(sample: Order, menu: Menu) -> None:
    data = menu.model_dump()
    coffee = next(i for i in data["items"] if i["id"] == "cold_coffee")
    next(s for s in coffee["sizes"] if s["id"] == "large")["price_paise"] += 1000
    dearer = Menu.model_validate(data)
    before = price_order(sample, menu).total_paise
    assert price_order(sample, dearer).total_paise == before + 1000


def test_empty_order_costs_nothing(menu: Menu) -> None:
    priced = price_order(state.new_order("s"), menu)
    assert (priced.lines, priced.total_paise) == ([], 0)


def test_item_removed_from_menu_is_an_error(menu: Menu) -> None:
    line = OrderLine(line_id=1, item_id="pizza", size_id=None, modifier_ids=[], quantity=1)
    stale = Order(session_id="s", lines=[line], next_line_id=2)
    with pytest.raises(OrderError) as info:
        price_order(stale, menu)
    assert info.value.code == ErrorCode.UNKNOWN_ITEM


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0"),
        (5, "₹0.05"),
        (1250, "₹12.50"),
        (19000, "₹190"),
        (116000, "₹1,160"),
        (12500000, "₹1,25,000"),
        (1234567800, "₹1,23,45,678"),
    ],
)
def test_format_inr(paise: int, text: str) -> None:
    assert format_inr(paise) == text


def test_format_inr_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        format_inr(-1)
