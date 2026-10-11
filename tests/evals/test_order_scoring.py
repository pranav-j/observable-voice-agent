"""Order scoring against scenario expectations, on hand-built orders."""

from typing import Any

import pytest
from evals.scenario import Expectation
from evals.scoring.order import phone_digits, score_order

from voice_order.order.models import Customer, Order, OrderLine, OrderStatus

ANIL = {"name": "Anil", "phone": "9000000001"}


def order(
    *lines: tuple[str, str | None, list[str], int],
    customer: dict[str, str] | None = ANIL,
    status: OrderStatus = "confirmed",
) -> Order:
    return Order(
        session_id="s",
        lines=[
            OrderLine(line_id=i, item_id=item, size_id=size, modifier_ids=sorted(mods), quantity=q)
            for i, (item, size, mods, q) in enumerate(lines, start=1)
        ],
        customer=Customer(**customer) if customer else None,
        status=status,
        next_line_id=len(lines) + 1,
    )


def expect(
    *items: dict[str, Any], customer: dict[str, str] | None = ANIL, status: str = "confirmed"
) -> Expectation:
    return Expectation.model_validate(
        {"status": status, "order": {"items": list(items), "customer": customer}}
    )


COFFEE_MEDIUM = {"item": "cold_coffee", "size": "medium", "quantity": 1}
TWO_DOSA = {"item": "masala_dosa", "quantity": 2}


def test_perfect_match() -> None:
    s = score_order(
        order(("cold_coffee", "medium", [], 1), ("masala_dosa", None, [], 2)),
        expect(COFFEE_MEDIUM, TWO_DOSA),
    )
    assert (s.exact_match, s.field_accuracy, s.task_success, s.mismatches) == (True, 1.0, True, ())


def test_line_order_does_not_matter() -> None:
    s = score_order(
        order(("masala_dosa", None, [], 2), ("cold_coffee", "medium", [], 1)),
        expect(COFFEE_MEDIUM, TWO_DOSA),
    )
    assert s.exact_match is True


def test_wrong_size() -> None:
    s = score_order(
        order(("cold_coffee", "large", [], 1), ("masala_dosa", None, [], 2)),
        expect(COFFEE_MEDIUM, TWO_DOSA),
    )
    assert s.exact_match is False
    assert not s.task_success
    # 10 fields: coffee 3/4 (size wrong), dosa 4/4, customer 2/2
    assert s.field_accuracy == pytest.approx(0.9)
    assert s.mismatches == ("missing: 1x cold_coffee (medium)", "extra: 1x cold_coffee (large)")


def test_wrong_quantity() -> None:
    s = score_order(
        order(("cold_coffee", "medium", [], 1), ("masala_dosa", None, [], 1)),
        expect(COFFEE_MEDIUM, TWO_DOSA),
    )
    assert s.mismatches == ("2x masala_dosa: got quantity 1",)
    assert s.field_accuracy == pytest.approx(0.9)


def test_missing_line() -> None:
    s = score_order(order(("cold_coffee", "medium", [], 1)), expect(COFFEE_MEDIUM, TWO_DOSA))
    assert s.mismatches == ("missing: 2x masala_dosa",)
    assert s.field_accuracy == pytest.approx(0.6)


def test_extra_line_breaks_exact_match_but_not_field_accuracy() -> None:
    s = score_order(
        order(
            ("cold_coffee", "medium", [], 1),
            ("masala_dosa", None, [], 2),
            ("affogato", None, [], 1),
        ),
        expect(COFFEE_MEDIUM, TWO_DOSA),
    )
    assert s.exact_match is False
    assert s.field_accuracy == 1.0
    assert s.mismatches == ("extra: 1x affogato",)


def test_wrong_item_earns_no_field_credit() -> None:
    s = score_order(order(("cold_brew", None, [], 2)), expect(TWO_DOSA, customer=None))
    assert s.field_accuracy == 0.0


def test_matching_is_optimal_not_greedy() -> None:
    # Greedy would pair the first expected line with the second actual line (3 fields)
    # and leave 1 field for the other pairing: 4/8. The best pairing scores 6/8.
    s = score_order(
        order(("cold_coffee", "small", [], 1), ("cold_coffee", "large", ["oat_milk"], 2)),
        expect(
            {"item": "cold_coffee", "size": "large", "quantity": 1},
            {"item": "cold_coffee", "size": "small", "quantity": 1},
            customer=None,
        ),
    )
    assert s.field_accuracy == pytest.approx(0.75)


def test_repeated_expected_items_are_merged() -> None:
    s = score_order(
        order(("masala_dosa", None, [], 2)),
        expect({"item": "masala_dosa"}, {"item": "masala_dosa"}),
    )
    assert s.exact_match is True


def test_modifier_order_does_not_matter() -> None:
    s = score_order(
        order(("cold_coffee", "large", ["oat_milk", "extra_shot"], 1)),
        expect({"item": "cold_coffee", "size": "large", "modifiers": ["oat_milk", "extra_shot"]}),
    )
    assert s.exact_match is True


# --- customer --------------------------------------------------------------------------


def test_name_ignores_case_and_spacing() -> None:
    s = score_order(
        order(
            ("masala_dosa", None, [], 2), customer={"name": " anil   KUMAR", "phone": "9000000001"}
        ),
        expect(TWO_DOSA, customer={"name": "Anil Kumar", "phone": "9000000001"}),
    )
    assert s.exact_match is True


def test_wrong_phone() -> None:
    s = score_order(
        order(("masala_dosa", None, [], 2), customer={"name": "Anil", "phone": "9000000009"}),
        expect(TWO_DOSA),
    )
    assert s.exact_match is False
    assert s.mismatches == ("customer phone: expected 9000000001, got 9000000009",)
    assert s.field_accuracy == pytest.approx(5 / 6)


def test_customer_not_set() -> None:
    s = score_order(order(("masala_dosa", None, [], 2), customer=None), expect(TWO_DOSA))
    assert s.mismatches == ("customer: not set",)
    assert s.field_accuracy == pytest.approx(4 / 6)


def test_phone_digits() -> None:
    assert phone_digits("+91 90000-00001") == "919000000001"
    assert phone_digits("90000 00001") == "9000000001"


# --- status ----------------------------------------------------------------------------


def test_right_order_wrong_status_is_not_success() -> None:
    s = score_order(order(("masala_dosa", None, [], 2), status="abandoned"), expect(TWO_DOSA))
    assert s.exact_match is True
    assert not s.task_success
    assert s.mismatches == ("status: expected confirmed, got abandoned",)


def test_status_only_scenario() -> None:
    expectation = Expectation.model_validate({"status": "escalated"})
    s = score_order(order(status="escalated"), expectation)
    assert (s.exact_match, s.field_accuracy) == (None, None)
    assert s.task_success
    assert s.escalated
    assert s.expected_escalation


def test_no_saved_order() -> None:
    s = score_order(None, expect(TWO_DOSA))
    assert s.status == "missing"
    assert not s.task_success
    assert s.exact_match is False
    assert s.mismatches[0] == "no order was saved for this session"
