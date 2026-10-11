"""Order invariants hold no matter how an Order is built (e.g. loaded from the database)."""

from typing import Any

import pytest
from pydantic import ValidationError

from voice_order.order.models import Order


def line(line_id: int, item_id: str = "masala_dosa", **overrides: Any) -> dict[str, Any]:
    base = {
        "line_id": line_id,
        "item_id": item_id,
        "size_id": None,
        "modifier_ids": [],
        "quantity": 1,
    }
    return base | overrides


def order(**overrides: Any) -> dict[str, Any]:
    return {"session_id": "s", "next_line_id": 10} | overrides


def test_valid_order() -> None:
    o = Order.model_validate(order(lines=[line(1), line(2, "pesarattu")]))
    assert len(o.lines) == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lines": [line(1), line(1, "pesarattu")]}, "duplicate line_id"),
        ({"lines": [line(1), line(2)]}, "same item, size and modifiers"),
        ({"lines": [line(10)]}, "next_line_id"),
        ({"mutation_seq": 2, "readback_seq": 3}, "readback_seq is ahead"),
        ({"lines": [line(1, modifier_ids=["oat_milk", "extra_shot"])]}, "sorted and unique"),
        ({"lines": [line(1, quantity=21)]}, "less than or equal to 20"),
        ({"customer": {"name": "Anil", "phone": "98765"}}, "pattern"),
        ({"status": "shipped"}, "status"),
    ],
)
def test_invariants(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Order.model_validate(order(**overrides))


def test_orders_round_trip_through_json() -> None:
    o = Order.model_validate(
        order(
            lines=[line(1, size_id="large", modifier_ids=["cheese"])],
            mutation_seq=3,
            readback_seq=3,
        )
    )
    assert Order.model_validate_json(o.model_dump_json()) == o
