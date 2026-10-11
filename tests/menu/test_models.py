"""Validation rules on the menu models."""

from typing import Any

import pytest
from pydantic import ValidationError

from voice_order.menu.models import Menu, MenuItem, normalize_name


def item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "masala_dosa",
        "name": "Masala Dosa",
        "category": "South Indian",
        "base_price_paise": 14000,
    }
    return base | overrides


def sized(**overrides: Any) -> dict[str, Any]:
    sizes = [
        {"id": "small", "name": "Small", "price_paise": 16000},
        {"id": "large", "name": "Large", "price_paise": 22000},
    ]
    return item(id="cappuccino", name="Cappuccino", base_price_paise=None, sizes=sizes) | overrides


def menu(*items: dict[str, Any]) -> dict[str, Any]:
    return {"restaurant": "Test Kitchen", "currency": "INR", "items": list(items)}


def test_valid_items_parse() -> None:
    m = Menu.model_validate(menu(item(), sized()))
    assert [i.id for i in m.items] == ["masala_dosa", "cappuccino"]
    assert not m.items[0].requires_size
    assert m.items[1].requires_size


def test_sized_item_must_not_have_base_price() -> None:
    with pytest.raises(ValidationError, match="must not set base_price_paise"):
        MenuItem.model_validate(sized(base_price_paise=19000))


def test_unsized_item_needs_base_price() -> None:
    with pytest.raises(ValidationError, match="need base_price_paise"):
        MenuItem.model_validate(item(base_price_paise=None))


@pytest.mark.parametrize("bad_id", ["Masala_Dosa", "masala-dosa", "1dosa", "", "dosa "])
def test_ids_must_be_snake_case(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        MenuItem.model_validate(item(id=bad_id))


@pytest.mark.parametrize("price", [14000.0, "14000", 0, -100])
def test_base_price_must_be_positive_int(price: object) -> None:
    with pytest.raises(ValidationError):
        MenuItem.model_validate(item(base_price_paise=price))


def test_modifier_price_may_be_zero_but_not_negative() -> None:
    free = {"id": "less_spicy", "name": "Less spicy", "price_paise": 0}
    assert MenuItem.model_validate(item(modifiers=[free])).modifiers[0].price_paise == 0
    with pytest.raises(ValidationError):
        MenuItem.model_validate(item(modifiers=[free | {"price_paise": -1}]))


def test_duplicate_size_and_modifier_ids_rejected() -> None:
    s = {"id": "small", "name": "Small", "price_paise": 100}
    with pytest.raises(ValidationError, match="duplicate size id"):
        MenuItem.model_validate(sized(sizes=[s, s]))
    mod = {"id": "cheese", "name": "Cheese", "price_paise": 3000}
    with pytest.raises(ValidationError, match="duplicate modifier id"):
        MenuItem.model_validate(item(modifiers=[mod, mod]))


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        MenuItem.model_validate(item(price=14000))


def test_duplicate_item_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate item id"):
        Menu.model_validate(menu(item(), item(name="Another Dosa")))


def test_alias_cannot_collide_with_another_items_name() -> None:
    clash = item(id="plain_dosa", name="Plain Dosa", aliases=["masala  DOSA"])
    with pytest.raises(ValidationError, match="name or alias used more than once"):
        Menu.model_validate(menu(item(), clash))


def test_menu_needs_items_and_inr() -> None:
    with pytest.raises(ValidationError):
        Menu.model_validate(menu())
    with pytest.raises(ValidationError):
        Menu.model_validate(menu(item()) | {"currency": "USD"})


def test_models_are_frozen() -> None:
    m = MenuItem.model_validate(item())
    with pytest.raises(ValidationError):
        m.in_stock = False  # type: ignore[misc]  # mypy catches this too; check runtime


def test_normalize_name() -> None:
    assert normalize_name("  Masala   DOSA ") == "masala dosa"
