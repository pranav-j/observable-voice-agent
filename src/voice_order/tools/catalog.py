"""The tools the agent can call, with the descriptions and schemas the LLM sees."""

from typing import Any

from pydantic import Field, field_validator

from voice_order.menu.models import MenuItem
from voice_order.menu.search import search
from voice_order.order.pricing import price_order
from voice_order.order.readback import describe_line, spoken_inr
from voice_order.tools.base import NoArgs, Result, Session, Tool, ToolArgs, ok

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
]

TOOLS: dict[str, Tool[Any]] = {t.name: t for t in ALL_TOOLS}
