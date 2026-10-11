"""The canonical read-back. The agent speaks this text word for word before confirming."""

import re

from pydantic import BaseModel, ConfigDict

from voice_order.menu.models import Menu
from voice_order.order.errors import ErrorCode, OrderError
from voice_order.order.models import Order
from voice_order.order.pricing import PricedLine, indian_grouping, price_order

# fmt: off
NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty",
]
# fmt: on


class Readback(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    total_paise: int
    mutation_seq: int  # the version of the order this read-back describes


def build_readback(order: Order, menu: Menu) -> Readback:
    """Items, total, name and phone, phrased for speech."""
    customer = order.customer
    if not order.lines or customer is None:
        missing = []
        if not order.lines:
            missing.append("at least one item")
        if customer is None:
            missing.append("the customer's name and phone number")
        raise OrderError(
            ErrorCode.ORDER_INCOMPLETE,
            "Before the read-back, collect " + " and ".join(missing) + ".",
        )

    priced = price_order(order, menu)
    sentences = [
        "Let me read that back.",
        *(describe_line(line) + "." for line in priced.lines),
        f"Your total is {spoken_inr(priced.total_paise)}.",
        f"The order is for {customer.name}, phone number {group_phone(customer.phone)}.",
        "Is that correct?",
    ]
    return Readback(
        text=" ".join(sentences),
        total_paise=priced.total_paise,
        mutation_seq=order.mutation_seq,
    )


def describe_line(line: PricedLine) -> str:
    """'Two large Cold Coffee with oat milk and extra shot'. Names are not pluralized."""
    words = [NUMBER_WORDS[line.quantity].capitalize()]
    if line.size_name:
        words.append(line.size_name.lower())
    words.append(spoken_name(line.name))
    text = " ".join(words)
    if line.modifier_names:
        text += " with " + join_words([m.lower() for m in line.modifier_names])
    note = pack_note(line.name, line.quantity)
    if note:
        # Without this, "Two Veg Samosa" sounds like two samosas, not two plates of two.
        text += f", {note}"
    return text


def spoken_name(name: str) -> str:
    """Drop notes in brackets: 'Veg Samosa (2 pcs)' -> 'Veg Samosa'."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


_PACK = re.compile(r"\((\d+)\s*pcs?\)", re.IGNORECASE)


def pack_note(name: str, quantity: int) -> str | None:
    """'(2 pcs)' in a name -> 'two pieces', or 'two pieces each' for more than one.

    Other bracket notes return None and stay unspoken.
    """
    match = _PACK.search(name)
    if match is None:
        return None
    count = int(match.group(1))
    word = NUMBER_WORDS[count] if count < len(NUMBER_WORDS) else str(count)
    pieces = f"{word} {'piece' if count == 1 else 'pieces'}"
    return f"{pieces} each" if quantity > 1 else pieces


def join_words(words: list[str]) -> str:
    """['a'] -> 'a', ['a', 'b'] -> 'a and b', ['a', 'b', 'c'] -> 'a, b and c'."""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def group_phone(phone: str) -> str:
    """'9000000001' -> '90000 00001'."""
    return f"{phone[:5]} {phone[5:]}"


def spoken_inr(paise: int) -> str:
    """116000 -> '1,160 rupees', 1250 -> '12 rupees 50 paise', 50 -> '50 paise'."""
    rupees, rest = divmod(paise, 100)
    parts = []
    if rupees or not rest:
        parts.append(f"{indian_grouping(rupees)} {'rupee' if rupees == 1 else 'rupees'}")
    if rest:
        parts.append(f"{rest} {'paisa' if rest == 1 else 'paise'}")
    return " ".join(parts)
