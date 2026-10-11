"""The seed menu in data/menu.json meets the constraints the agent and evals rely on."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from voice_order.menu.loader import DEFAULT_MENU_PATH, load_menu
from voice_order.menu.models import Menu, normalize_name

# Pairs a caller (or the STT) can easily mix up. Eval scenarios use these.
CONFUSABLE_PAIRS = [
    ("paneer_tikka", "paneer_tikka_roll"),
    ("masala_dosa", "mysore_masala_dosa"),
    ("cold_coffee", "cold_brew"),
    ("cafe_latte", "chai_latte"),
]
# Names speech-to-text tends to mangle.
STT_HARD = ["pesarattu", "bisi_bele_bath", "affogato"]


def test_item_count(menu: Menu) -> None:
    assert 25 <= len(menu.items) <= 30


def test_enough_items_with_sizes(menu: Menu) -> None:
    assert sum(i.requires_size for i in menu.items) >= 6


def test_enough_items_with_modifiers(menu: Menu) -> None:
    assert sum(bool(i.modifiers) for i in menu.items) >= 6


def test_exactly_three_out_of_stock(menu: Menu) -> None:
    assert sorted(i.id for i in menu.items if not i.in_stock) == [
        "blueberry_cheesecake",
        "mango_lassi",
        "mutton_rogan_josh",
    ]


def test_out_of_stock_items_have_in_stock_alternatives(menu: Menu) -> None:
    for gone in (i for i in menu.items if not i.in_stock):
        same_category = [i for i in menu.items if i.category == gone.category and i.in_stock]
        assert same_category, f"{gone.id} has no in-stock item in {gone.category!r}"


def test_confusable_pairs_exist_and_overlap(menu: Menu) -> None:
    names = {i.id: normalize_name(i.name) for i in menu.items}
    for a, b in CONFUSABLE_PAIRS:
        assert a in names
        assert b in names
        assert set(names[a].split()) & set(names[b].split()), f"{a} / {b} share no words"


def test_stt_hard_items_exist(menu: Menu) -> None:
    ids = {i.id for i in menu.items}
    assert set(STT_HARD) <= ids


def test_common_aliases_resolve(menu: Menu) -> None:
    by_alias = {normalize_name(a): i.id for i in menu.items for a in i.aliases}
    assert by_alias["iced coffee"] == "cold_coffee"
    assert by_alias["nimbu soda"] == "fresh_lime_soda"
    assert sum(bool(i.aliases) for i in menu.items) >= 10


def test_loader_rejects_float_price_in_json(tmp_path: Path) -> None:
    text = DEFAULT_MENU_PATH.read_text(encoding="utf-8")
    broken = tmp_path / "menu.json"
    broken.write_text(text.replace('"base_price_paise": 15000', '"base_price_paise": 150.5', 1))
    with pytest.raises(ValidationError, match="base_price_paise"):
        load_menu(broken)
