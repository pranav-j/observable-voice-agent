"""Score a final order against a scenario's expectation. Pure functions, no I/O."""

import re
from collections import Counter
from dataclasses import dataclass
from functools import cache

from evals.scenario import Expectation, ExpectedOrder
from voice_order.menu.models import normalize_name
from voice_order.order.models import Order

LineKey = tuple[str, str | None, tuple[str, ...]]
FIELDS_PER_LINE = 4  # item, size, modifiers, quantity
FIELDS_PER_CUSTOMER = 2  # name, phone


@dataclass(frozen=True)
class Line:
    item: str
    size: str | None
    modifiers: tuple[str, ...]  # sorted
    quantity: int

    @property
    def key(self) -> LineKey:
        return (self.item, self.size, self.modifiers)

    def describe(self) -> str:
        text = f"{self.quantity}x {self.item}"
        if self.size:
            text += f" ({self.size})"
        if self.modifiers:
            text += f" with {', '.join(self.modifiers)}"
        return text


@dataclass(frozen=True)
class OrderScore:
    status: str  # "missing" when no order was saved
    expected_status: str
    exact_match: bool | None  # None when the scenario doesn't score the order's contents
    field_accuracy: float | None
    task_success: bool
    escalated: bool
    expected_escalation: bool
    mismatches: tuple[str, ...]


def expected_lines(expected: ExpectedOrder) -> list[Line]:
    """Expected lines, with repeats of the same product merged (as the order does)."""
    quantities: Counter[LineKey] = Counter()
    for e in expected.items:
        quantities[(e.item, e.size, tuple(sorted(set(e.modifiers))))] += e.quantity
    return [Line(*key, quantity=q) for key, q in quantities.items()]


def actual_lines(order: Order) -> list[Line]:
    return [
        Line(x.item_id, x.size_id, tuple(sorted(x.modifier_ids)), x.quantity) for x in order.lines
    ]


def phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def score_order(order: Order | None, expect: Expectation) -> OrderScore:
    status = order.status if order else "missing"
    status_ok = status == expect.status
    mismatches: list[str] = []
    if order is None:
        mismatches.append("no order was saved for this session")
    elif not status_ok:
        mismatches.append(f"status: expected {expect.status}, got {status}")

    exact: bool | None = None
    accuracy: float | None = None
    if expect.order is not None:
        want = expected_lines(expect.order)
        got = actual_lines(order) if order else []
        line_problems = _line_mismatches(want, got)
        customer_problems = _customer_mismatches(order, expect.order)
        mismatches += line_problems + customer_problems
        exact = order is not None and not line_problems and not customer_problems
        accuracy = _field_accuracy(want, got, order, expect.order)

    return OrderScore(
        status=status,
        expected_status=expect.status,
        exact_match=exact,
        field_accuracy=accuracy,
        task_success=status_ok and exact is not False,
        escalated=status == "escalated",
        expected_escalation=expect.status == "escalated",
        mismatches=tuple(mismatches),
    )


def _line_mismatches(want: list[Line], got: list[Line]) -> list[str]:
    want_q = {x.key: x.quantity for x in want}
    got_q = {x.key: x.quantity for x in got}
    problems = []
    for line in want:
        if line.key not in got_q:
            problems.append(f"missing: {line.describe()}")
        elif got_q[line.key] != line.quantity:
            problems.append(f"{line.describe()}: got quantity {got_q[line.key]}")
    problems += [f"extra: {x.describe()}" for x in got if x.key not in want_q]
    return problems


def _customer_mismatches(order: Order | None, expected: ExpectedOrder) -> list[str]:
    if expected.customer is None or order is None:
        return []
    if order.customer is None:
        return ["customer: not set"]
    problems = []
    if normalize_name(order.customer.name) != normalize_name(expected.customer.name):
        problems.append(
            f"customer name: expected {expected.customer.name!r}, got {order.customer.name!r}"
        )
    phone = expected.customer.phone
    if phone is not None and phone_digits(order.customer.phone) != phone_digits(phone):
        problems.append(
            f"customer phone: expected {expected.customer.phone}, got {order.customer.phone}"
        )
    return problems


def _field_accuracy(
    want: list[Line], got: list[Line], order: Order | None, expected: ExpectedOrder
) -> float:
    total = FIELDS_PER_LINE * len(want)
    correct = _best_matching(tuple(want), tuple(got))
    if expected.customer is not None:
        phone = expected.customer.phone
        total += FIELDS_PER_CUSTOMER if phone is not None else 1  # no phone: the name only
        if order is not None and order.customer is not None:
            correct += normalize_name(order.customer.name) == normalize_name(expected.customer.name)
            if phone is not None:
                correct += phone_digits(order.customer.phone) == phone_digits(phone)
    return correct / total if total else 1.0


def _credit(want: Line, got: Line) -> int:
    """Correct fields if `got` stands in for `want`. A wrong item earns nothing."""
    if got.item != want.item:
        return 0
    return (
        1
        + (got.size == want.size)
        + (got.modifiers == want.modifiers)
        + (got.quantity == want.quantity)
    )


def _best_matching(want: tuple[Line, ...], got: tuple[Line, ...]) -> int:
    """Most correct fields over all one-to-one pairings of expected to actual lines.

    Dynamic programming over (next expected line, set of actual lines already used),
    with the used set as a bitmask. Exact, and fast for the handful of lines an order has.
    """

    @cache
    def best(i: int, used: int) -> int:
        if i == len(want):
            return 0
        options = [best(i + 1, used)]  # leave expected line i unmatched
        for j, line in enumerate(got):
            if not used & (1 << j):
                options.append(_credit(want[i], line) + best(i + 1, used | (1 << j)))
        return max(options)

    return best(0, 0)
