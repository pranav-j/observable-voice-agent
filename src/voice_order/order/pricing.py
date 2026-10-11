"""Prices, computed from the menu at call time. Orders themselves store no prices."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from voice_order.menu.models import Menu, MenuItem
from voice_order.order.errors import ErrorCode, OrderError
from voice_order.order.models import Order, OrderLine


class PricedLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_id: int
    item_id: str
    name: str
    size_name: str | None
    modifier_names: list[str]  # in menu order
    quantity: int
    unit_price_paise: int
    line_total_paise: int


class PricedOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    lines: list[PricedLine]
    total_paise: int


def unit_price_paise(item: MenuItem, size_id: str | None, modifier_ids: Iterable[str]) -> int:
    """Base or size price plus modifier surcharges, for one unit."""
    if size_id is None:
        if item.base_price_paise is None:
            raise OrderError(ErrorCode.SIZE_REQUIRED, f"{item.name} needs a size.")
        price = item.base_price_paise
    else:
        size = next((s for s in item.sizes if s.id == size_id), None)
        if size is None:
            raise OrderError(ErrorCode.INVALID_SIZE, f"{size_id!r} is not a size of {item.name}.")
        price = size.price_paise
    surcharges = {m.id: m.price_paise for m in item.modifiers}
    for modifier_id in modifier_ids:
        if modifier_id not in surcharges:
            raise OrderError(
                ErrorCode.INVALID_MODIFIER, f"{modifier_id!r} is not available for {item.name}."
            )
        price += surcharges[modifier_id]
    return price


def price_line(line: OrderLine, menu: Menu) -> PricedLine:
    item = menu.item(line.item_id)
    if item is None:
        raise OrderError(ErrorCode.UNKNOWN_ITEM, f"{line.item_id!r} is no longer on the menu.")
    unit = unit_price_paise(item, line.size_id, line.modifier_ids)
    size_name = next((s.name for s in item.sizes if s.id == line.size_id), None)
    return PricedLine(
        line_id=line.line_id,
        item_id=item.id,
        name=item.name,
        size_name=size_name,
        modifier_names=[m.name for m in item.modifiers if m.id in line.modifier_ids],
        quantity=line.quantity,
        unit_price_paise=unit,
        line_total_paise=unit * line.quantity,
    )


def price_order(order: Order, menu: Menu) -> PricedOrder:
    lines = [price_line(line, menu) for line in order.lines]
    return PricedOrder(lines=lines, total_paise=sum(x.line_total_paise for x in lines))


def format_inr(paise: int) -> str:
    """19000 -> '₹190', 1250 -> '₹12.50', 12500000 -> '₹1,25,000' (Indian digit grouping)."""
    if paise < 0:
        raise ValueError("amount cannot be negative")
    rupees, rest = divmod(paise, 100)
    return f"₹{indian_grouping(rupees)}" + (f".{rest:02d}" if rest else "")


def indian_grouping(n: int) -> str:
    """1160 -> '1,160', 125000 -> '1,25,000': last three digits, then pairs."""
    digits = str(n)
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([*groups, tail])
