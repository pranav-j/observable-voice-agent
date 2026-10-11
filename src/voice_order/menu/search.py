"""Fuzzy menu search over item names and aliases."""

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz, utils

from voice_order.menu.models import Menu, MenuItem


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: MenuItem
    score: float  # 0-100; 100 means an exact name or alias match
    matched: str  # the name or alias that scored best


def search(menu: Menu, query: str, limit: int = 5) -> list[SearchHit]:
    """Rank menu items against `query`, best first.

    Never returns an empty list for a non-blank query: weak matches come back
    with low scores so the caller can decide what to do with them.
    """
    if not utils.default_process(query):
        raise ValueError("query is blank")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    hits = []
    for item in menu.items:
        # On a tie, max() keeps the first candidate, so the real name beats an alias.
        score, matched = max(
            ((_score(query, name), name) for name in (item.name, *item.aliases)),
            key=lambda pair: pair[0],
        )
        hits.append(SearchHit(item=item, score=round(score, 1), matched=matched))

    # Stable sort: equal scores keep menu order, so results are deterministic.
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def _score(query: str, candidate: str) -> float:
    """Similarity from 0 to 100 that never matches inside a word.

    `ratio` compares whole strings and absorbs STT misspellings ("pesaratu").
    `token_set_ratio` compares word sets, so "samosa" matches "Veg Samosa (2 pcs)"
    and word order doesn't matter; it's scaled to 95 so exact matches stay on top.
    We avoid rapidfuzz's WRatio because its character-level partial match finds
    "latte" inside "sushi platter" and scores it 90.
    """
    p = utils.default_process
    return max(
        fuzz.ratio(query, candidate, processor=p),
        0.95 * fuzz.token_set_ratio(query, candidate, processor=p),
    )
