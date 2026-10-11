"""The tools the agent can call, with the descriptions and schemas the LLM sees."""

from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator, model_validator

from voice_order.menu.models import MenuItem
from voice_order.menu.search import search
from voice_order.order import state
from voice_order.order.models import Order
from voice_order.order.pricing import price_order
from voice_order.order.readback import build_readback, describe_line, group_phone, spoken_inr
from voice_order.tools.base import CallEnd, EndKind, NoArgs, Result, Session, Tool, ToolArgs, ok

# Measured on the seed menu: real matches score 93+, items not on the menu stay under 75.
STRONG_MATCH = 90
WEAK_MATCH = 80
SEARCH_LIMIT = 5


# --- views: how menu items and orders are shown to the LLM ------------------------


def price_text(paise: int) -> str:
    return "free" if paise == 0 else spoken_inr(paise)


def item_view(item: MenuItem) -> dict[str, Any]:
    view: dict[str, Any] = {
        "item_id": item.id,
        "name": item.name,
        "category": item.category,
        "in_stock": item.in_stock,
    }
    if item.sizes:
        view["size_required"] = True
        view["sizes"] = [
            {"size_id": s.id, "name": s.name, "price": price_text(s.price_paise)}
            for s in item.sizes
        ]
    elif item.base_price_paise is not None:
        view["price"] = price_text(item.base_price_paise)
    if item.modifiers:
        view["modifiers"] = [
            {"modifier_id": m.id, "name": m.name, "price": price_text(m.price_paise)}
            for m in item.modifiers
        ]
    return view


def order_view(session: Session) -> dict[str, Any]:
    order = session.order
    priced = price_order(order, session.menu)
    return {
        "status": order.status,
        "lines": [
            {
                "line_id": p.line_id,
                "description": describe_line(p),
                "item_id": line.item_id,
                "size_id": line.size_id,
                "modifier_ids": line.modifier_ids,
                "quantity": line.quantity,
                "line_total": price_text(p.line_total_paise),
            }
            for line, p in zip(order.lines, priced.lines, strict=True)
        ],
        "total": spoken_inr(priced.total_paise),
        "customer": order.customer.model_dump() if order.customer else None,
        "readback_current": order.readback_seq is not None and order.readback_is_current,
    }


def match_label(score: float) -> str:
    if score == 100:
        return "exact"
    if score >= STRONG_MATCH:
        return "strong"
    if score >= WEAK_MATCH:
        return "possible"
    return "weak"


# --- search_menu ---------------------------------------------------------------------


class SearchMenuArgs(ToolArgs):
    query: str = Field(
        description="What the caller asked for, e.g. 'large cold coffee' or 'paneer roll'."
    )

    @field_validator("query")
    @classmethod
    def _has_words(cls, value: str) -> str:
        if not any(ch.isalnum() for ch in value):
            raise ValueError("query must contain letters or digits")
        return value


def search_menu(session: Session, args: SearchMenuArgs) -> Result:
    hits = search(session.menu, args.query, limit=SEARCH_LIMIT)
    matches = [
        {"match": match_label(h.score), "score": h.score, "matched_on": h.matched}
        | item_view(h.item)
        for h in hits
    ]
    top = hits[0].score
    notes = []
    if top < WEAK_MATCH:
        notes.append(f"No close match for {args.query!r}; it is probably not on the menu.")
    elif top < 100 and sum(h.score == top for h in hits) > 1:
        notes.append("Several items match equally well; ask the caller which one they mean.")
    return ok(matches=matches, **({"note": " ".join(notes)} if notes else {}))


# --- get_order_summary -------------------------------------------------------------------


def get_order_summary(session: Session, args: NoArgs) -> Result:
    return ok(
        order=order_view(session),
        note="This is not the read-back. Before confirming, call get_readback.",
    )


# --- order changes -----------------------------------------------------------------------


def _changed(session: Session, new: Order, **extra: Any) -> Result:
    """Install the new order and return its view, warning if a read-back just went stale."""
    old = session.order
    session.order = new
    payload: dict[str, Any] = {"order": order_view(session), **extra}
    if old.readback_seq is not None and old.readback_is_current and not new.readback_is_current:
        payload["note"] = (
            "The order changed after the read-back. Call get_readback again before confirming."
        )
    return ok(**payload)


class AddItemArgs(ToolArgs):
    item_id: str = Field(description="Item id from search_menu, e.g. 'masala_dosa'.")
    quantity: int = Field(description="How many, from 1 to 20.")
    size_id: str | None = Field(
        default=None,
        description="Size id from search_menu. Required when the item has sizes; omit otherwise.",
    )
    modifier_ids: list[str] = Field(
        default_factory=list,
        description="Modifier ids from search_menu, e.g. ['oat_milk']. Empty for none.",
    )


def add_item(session: Session, args: AddItemArgs) -> Result:
    new = state.add_line(
        session.order, session.menu, args.item_id, args.quantity, args.size_id, args.modifier_ids
    )
    return _changed(session, new)


class UpdateItemArgs(ToolArgs):
    line_id: int = Field(description="Line id from the order, as shown in get_order_summary.")
    quantity: int | None = Field(default=None, description="New quantity, 1 to 20. Omit to keep.")
    size_id: str | None = Field(default=None, description="New size id. Omit to keep.")
    modifier_ids: list[str] | None = Field(
        default=None,
        description="Replaces all modifiers on the line. [] removes them. Omit to keep.",
    )

    @model_validator(mode="before")
    @classmethod
    def _cannot_change_the_item(cls, data: Any) -> Any:
        # Models try update_item(item_id=...) to swap a latte for a cappuccino. A generic
        # "extra input" error left one telling the caller it couldn't be done.
        if isinstance(data, dict) and "item_id" in data:
            raise ValueError(
                "update_item can't change the item itself. To swap it, call remove_item "
                "for this line, then add_item for the new item."
            )
        return data


def update_item(session: Session, args: UpdateItemArgs) -> Result:
    new = state.update_line(
        session.order, session.menu, args.line_id, args.quantity, args.size_id, args.modifier_ids
    )
    return _changed(session, new)


class RemoveItemArgs(ToolArgs):
    line_id: int = Field(description="Line id from the order, as shown in get_order_summary.")


def remove_item(session: Session, args: RemoveItemArgs) -> Result:
    return _changed(session, state.remove_line(session.order, args.line_id))


class SetCustomerArgs(ToolArgs):
    name: str = Field(description="The name for the order, as the caller gave it.")
    phone: str = Field(
        description=(
            "The caller's phone number exactly as they said it, in digits or words. "
            "Spaces, +91 and spoken forms like 'nine double zero' are fine."
        )
    )


def set_customer(session: Session, args: SetCustomerArgs) -> Result:
    new = state.set_customer(session.order, args.name, args.phone)
    phone = group_phone(new.customer.phone) if new.customer else None
    return _changed(session, new, read_phone_back_as=phone)


# --- read-back, confirmation and ending the call ---------------------------------------------


def get_readback(session: Session, args: NoArgs) -> Result:
    marked = state.mark_readback(session.order)  # ORDER_CLOSED if already closed
    readback = build_readback(marked, session.menu)  # ORDER_INCOMPLETE if not ready
    session.order = marked  # recorded only once the read-back exists
    return ok(
        readback=readback.text,
        instructions=(
            "Say the read-back to the caller word for word, then wait for a clear yes before "
            "calling confirm_order. If they change anything, update the order and call "
            "get_readback again."
        ),
    )


def confirm_order(session: Session, args: NoArgs) -> Result:
    session.order = state.confirm(session.order)
    return ok(
        order=order_view(session),
        instructions=(
            "The order is placed. Tell the caller it will be ready for pickup, thank them and "
            "say goodbye, then call end_call."
        ),
    )


class ReasonArgs(ToolArgs):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="A short reason, e.g. 'caller asked for a person twice'."
    )


def _end(session: Session, kind: EndKind, reason: str) -> None:
    if session.ending is None:  # the first ending wins
        session.ending = CallEnd(kind=kind, reason=reason)


def transfer_to_human(session: Session, args: ReasonArgs) -> Result:
    session.order = state.escalate(session.order)
    _end(session, "transfer", args.reason)
    return ok(
        status=session.order.status,
        instructions="Tell the caller you are connecting them to a team member, then stop.",
    )


def end_call(session: Session, args: ReasonArgs) -> Result:
    session.order = state.abandon(session.order)
    _end(session, "end_call", args.reason)
    return ok(
        status=session.order.status,
        instructions="Say a short goodbye if you haven't already. The call will end.",
    )


# --- registry --------------------------------------------------------------------------

# Annotated: Tool is invariant in its args type, so mypy would infer list[object].
ALL_TOOLS: list[Tool[Any]] = [
    Tool(
        name="search_menu",
        description=(
            "Look up menu items by what the caller said. Returns up to 5 ranked matches "
            "with item ids, stock, sizes, modifiers and prices. Use it before adding any "
            "item and for every question about the menu or prices. Each match is labelled "
            "exact, strong, possible, or weak (probably not on the menu)."
        ),
        args_model=SearchMenuArgs,
        handler=search_menu,
    ),
    Tool(
        name="get_order_summary",
        description=(
            "Show the current order: lines with their line ids, prices, the total, and the "
            "customer. Use it to check the order or answer what the caller has so far. "
            "It is not the read-back; before confirming, call get_readback."
        ),
        args_model=NoArgs,
        handler=get_order_summary,
    ),
    Tool(
        name="add_item",
        description=(
            "Add an item to the order, using item_id, size_id and modifier_ids exactly as "
            "search_menu returned them. Adding an identical item again raises its quantity. "
            "Returns the updated order."
        ),
        args_model=AddItemArgs,
        handler=add_item,
    ),
    Tool(
        name="update_item",
        description=(
            "Change the quantity, size or modifiers of a line in the order. Arguments you leave "
            "out stay the same; modifier_ids replaces the whole list. Returns the updated order."
        ),
        args_model=UpdateItemArgs,
        handler=update_item,
    ),
    Tool(
        name="remove_item",
        description="Remove a line from the order by its line id. Returns the updated order.",
        args_model=RemoveItemArgs,
        handler=remove_item,
    ),
    Tool(
        name="set_customer",
        description=(
            "Save the caller's name and 10-digit phone number for the order. Then read the "
            "number back to the caller in the grouped form this returns."
        ),
        args_model=SetCustomerArgs,
        handler=set_customer,
    ),
    Tool(
        name="get_readback",
        description=(
            "Get the official read-back of the order: items, total, name and phone. Call it "
            "once the items and the caller's details are complete, speak it word for word, "
            "and wait for a clear yes. Any change afterwards needs a new read-back."
        ),
        args_model=NoArgs,
        handler=get_readback,
    ),
    Tool(
        name="confirm_order",
        description=(
            "Place the order. Only call it after the caller clearly said yes to the read-back "
            "from get_readback, with no changes since."
        ),
        args_model=NoArgs,
        handler=confirm_order,
    ),
    Tool(
        name="transfer_to_human",
        description=(
            "Hand the call to a team member. Use it if the caller asks for a person twice, or "
            "after three failed attempts at the same step."
        ),
        args_model=ReasonArgs,
        handler=transfer_to_human,
    ),
    Tool(
        name="end_call",
        description=(
            "End the call. Use it after saying goodbye, or when the caller hangs up or wants "
            "to stop. An order that was not confirmed is dropped."
        ),
        args_model=ReasonArgs,
        handler=end_call,
    ),
]

TOOLS: dict[str, Tool[Any]] = {t.name: t for t in ALL_TOOLS}
