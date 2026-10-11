"""Order state machine.

Every operation takes an Order and returns a new one; nothing is changed in place.
Invalid requests raise OrderError, which the tools layer reports back to the LLM.
"""

import re
from collections.abc import Iterable
from typing import Any

from voice_order.menu.models import Menu, MenuItem
from voice_order.order.errors import ErrorCode, OrderError
from voice_order.order.models import MAX_QUANTITY, Customer, Order, OrderLine

MAX_ALTERNATIVES = 3


def new_order(session_id: str) -> Order:
    return Order(session_id=session_id)


def add_line(
    order: Order,
    menu: Menu,
    item_id: str,
    quantity: int,
    size_id: str | None = None,
    modifier_ids: Iterable[str] = (),
) -> Order:
    """Add an item. An identical line (same item, size, modifiers) gets its quantity raised."""
    _require_draft(order)
    item = _require_item(menu, item_id)
    if not item.in_stock:
        raise OrderError(
            ErrorCode.OUT_OF_STOCK,
            f"{item.name} is out of stock.",
            alternatives=_alternatives(menu, item),
        )
    _check_quantity(quantity)
    line = OrderLine(
        line_id=order.next_line_id,
        item_id=item.id,
        size_id=_check_size(item, size_id),
        modifier_ids=_check_modifiers(item, modifier_ids),
        quantity=quantity,
    )
    existing = next((x for x in order.lines if x.key == line.key), None)
    if existing is None:
        return _mutate(order, lines=[*order.lines, line], next_line_id=order.next_line_id + 1)
    merged = _with(existing, quantity=_merged_quantity(existing.quantity, quantity))
    return _mutate(order, lines=[merged if x is existing else x for x in order.lines])


def update_line(
    order: Order,
    menu: Menu,
    line_id: int,
    quantity: int | None = None,
    size_id: str | None = None,
    modifier_ids: Iterable[str] | None = None,
) -> Order:
    """Change a line. Arguments left as None stay as they are; modifier_ids=[] clears them."""
    _require_draft(order)
    line = _require_line(order, line_id)
    item = _require_item(menu, line.item_id)
    if quantity is not None:
        _check_quantity(quantity)
    updated = _with(
        line,
        quantity=line.quantity if quantity is None else quantity,
        size_id=line.size_id if size_id is None else _check_size(item, size_id),
        modifier_ids=(
            line.modifier_ids if modifier_ids is None else _check_modifiers(item, modifier_ids)
        ),
    )
    if updated == line:
        return order  # nothing changed, so an existing read-back stays valid

    # If the change makes this line identical to another one, fold it into that line.
    twin = next((x for x in order.lines if x.key == updated.key and x is not line), None)
    if twin is not None:
        merged = _with(twin, quantity=_merged_quantity(twin.quantity, updated.quantity))
        lines = [merged if x is twin else x for x in order.lines if x is not line]
    else:
        lines = [updated if x is line else x for x in order.lines]
    return _mutate(order, lines=lines)


def remove_line(order: Order, line_id: int) -> Order:
    _require_draft(order)
    line = _require_line(order, line_id)
    return _mutate(order, lines=[x for x in order.lines if x is not line])


def set_customer(order: Order, name: str, phone: str) -> Order:
    _require_draft(order)
    clean_name = spelled_name(name) or " ".join(name.split())
    if not clean_name:
        raise OrderError(ErrorCode.INVALID_NAME, "The customer name is empty.")
    digits = normalize_phone(phone)
    if digits is None:
        raise OrderError(
            ErrorCode.INVALID_PHONE,
            f"{phone!r} is not a 10-digit phone number.",
        )
    customer = Customer(name=clean_name, phone=digits)
    if customer == order.customer:
        return order
    return _mutate(order, customer=customer)


DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}  # fmt: skip
REPEAT_WORDS = {"double": 2, "triple": 3}


def normalize_phone(raw: str) -> str | None:
    """Ten digits from what the caller said, or None.

    Takes digits or spoken words ("nine double zero ..."). Accepts a +91 or leading-0
    prefix if ten digits remain, and rejects numbers that still start with 0, since no
    Indian number does once the prefix is gone.
    """
    digits = spoken_digits(raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] != "0" else None


def spelled_name(raw: str) -> str | None:
    """'K-A-V-Y-A' or 'K A V Y A' -> 'Kavya'. None if it isn't spelled letter by letter.

    Speech recognition turns unusual names into common words ("Kavya" became "Caviar"),
    so callers spell them. The letters are what the caller meant.
    """
    letters = re.split(r"[\s.\-]+", raw.strip())
    if len(letters) < 2 or not all(len(x) == 1 and x.isalpha() for x in letters):
        return None
    return "".join(letters).capitalize()


def spoken_digits(raw: str) -> str:
    """'nine double zero, 12' -> '900012'. Other words ("my number is") are ignored.

    Counting repeated words is easy in code and error-prone for a language model,
    so the model passes the caller's words through and this does the counting.
    """
    out: list[str] = []
    repeat = 1
    for token in re.findall(r"[a-z]+|\d+", raw.lower()):
        if token in REPEAT_WORDS:
            repeat = REPEAT_WORDS[token]
            continue
        digit = token if token.isdigit() else DIGIT_WORDS.get(token)
        if digit is not None:
            out.append(digit[0] * repeat + digit[1:])
        repeat = 1
    return "".join(out)


def mark_readback(order: Order) -> Order:
    """Record that the read-back was fetched for the order as it is now."""
    _require_draft(order)
    return _replace(order, readback_seq=order.mutation_seq)


def confirm(order: Order) -> Order:
    """Confirm only with items, a customer, and a read-back fetched after the last change."""
    _require_draft(order)
    missing = []
    if not order.lines:
        missing.append("the order has no items")
    if order.customer is None:
        missing.append("the customer's name and phone are not set")
    if order.readback_seq is None:
        missing.append("the read-back has not been given")
    elif not order.readback_is_current:
        missing.append("the order changed after the last read-back")
    if missing:
        raise OrderError(ErrorCode.READBACK_REQUIRED, "Cannot confirm: " + "; ".join(missing) + ".")
    return _replace(order, status="confirmed")


def escalate(order: Order) -> Order:
    """Hand off to a human. A confirmed order stays confirmed."""
    return _replace(order, status="escalated") if order.status == "draft" else order


def abandon(order: Order) -> Order:
    """The call ended without confirming. A confirmed order stays confirmed."""
    return _replace(order, status="abandoned") if order.status == "draft" else order


# --- helpers ---------------------------------------------------------------


def _replace(order: Order, **changes: Any) -> Order:
    # model_copy(update=...) would skip validation; rebuilding runs the invariant checks.
    return Order.model_validate({**dict(order), **changes})


def _mutate(order: Order, **changes: Any) -> Order:
    return _replace(order, mutation_seq=order.mutation_seq + 1, **changes)


def _with(line: OrderLine, **changes: Any) -> OrderLine:
    return OrderLine.model_validate({**dict(line), **changes})


def _require_draft(order: Order) -> None:
    if order.status != "draft":
        raise OrderError(ErrorCode.ORDER_CLOSED, f"The order is already {order.status}.")


def _require_item(menu: Menu, item_id: str) -> MenuItem:
    item = menu.item(item_id)
    if item is None:
        raise OrderError(
            ErrorCode.UNKNOWN_ITEM,
            f"No menu item with id {item_id!r}. Use search_menu to find the right id.",
        )
    return item


def _require_line(order: Order, line_id: int) -> OrderLine:
    line = next((x for x in order.lines if x.line_id == line_id), None)
    if line is None:
        ids = ", ".join(str(x.line_id) for x in order.lines) or "none"
        raise OrderError(ErrorCode.UNKNOWN_LINE, f"No line {line_id}. Current lines: {ids}.")
    return line


def _check_quantity(quantity: int) -> None:
    if not 1 <= quantity <= MAX_QUANTITY:
        raise OrderError(
            ErrorCode.INVALID_QUANTITY, f"Quantity must be between 1 and {MAX_QUANTITY}."
        )


def _merged_quantity(current: int, extra: int) -> int:
    total = current + extra
    if total > MAX_QUANTITY:
        raise OrderError(
            ErrorCode.INVALID_QUANTITY,
            f"That would make {total}; the limit is {MAX_QUANTITY} per item.",
        )
    return total


def _check_size(item: MenuItem, size_id: str | None) -> str | None:
    valid = [s.id for s in item.sizes]
    if size_id is None:
        if valid:
            raise OrderError(
                ErrorCode.SIZE_REQUIRED,
                f"{item.name} needs a size: {', '.join(valid)}.",
            )
        return None
    if size_id not in valid:
        detail = f"sizes are {', '.join(valid)}" if valid else "it doesn't come in sizes"
        raise OrderError(
            ErrorCode.INVALID_SIZE, f"{size_id!r} is not valid for {item.name}; {detail}."
        )
    return size_id


def _check_modifiers(item: MenuItem, modifier_ids: Iterable[str]) -> list[str]:
    wanted = sorted(set(modifier_ids))
    valid = {m.id for m in item.modifiers}
    bad = [m for m in wanted if m not in valid]
    if bad:
        options = ", ".join(sorted(valid)) or "none"
        raise OrderError(
            ErrorCode.INVALID_MODIFIER,
            f"{', '.join(bad)} not available for {item.name}. Options: {options}.",
        )
    return wanted


def _alternatives(menu: Menu, item: MenuItem) -> tuple[str, ...]:
    same_category = (
        i.id for i in menu.items if i.category == item.category and i.in_stock and i is not item
    )
    return tuple(same_category)[:MAX_ALTERNATIVES]
