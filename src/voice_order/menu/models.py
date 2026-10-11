"""Menu models. Prices are integer paise (1 INR = 100 paise); floats never touch money."""

from collections import Counter
from collections.abc import Iterable
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PricePaise = Annotated[int, Field(gt=0)]
SurchargePaise = Annotated[int, Field(ge=0)]


class _Frozen(BaseModel):
    # strict: "12000" or 120.0 in the JSON is an error, not silently coerced to int.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Size(_Frozen):
    id: Slug
    name: Name
    price_paise: PricePaise


class Modifier(_Frozen):
    id: Slug
    name: Name
    price_paise: SurchargePaise


class MenuItem(_Frozen):
    id: Slug
    name: Name
    aliases: list[Name] = []
    category: Name
    base_price_paise: PricePaise | None  # None when sizes define the price
    sizes: list[Size] = []
    modifiers: list[Modifier] = []
    in_stock: bool = True

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.sizes and self.base_price_paise is not None:
            raise ValueError(f"{self.id}: items with sizes must not set base_price_paise")
        if not self.sizes and self.base_price_paise is None:
            raise ValueError(f"{self.id}: items without sizes need base_price_paise")
        _require_unique((s.id for s in self.sizes), f"{self.id}: duplicate size id")
        _require_unique((m.id for m in self.modifiers), f"{self.id}: duplicate modifier id")
        return self

    @property
    def requires_size(self) -> bool:
        return bool(self.sizes)


class Menu(_Frozen):
    restaurant: Name
    currency: Literal["INR"]
    items: list[MenuItem] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Self:
        _require_unique((i.id for i in self.items), "duplicate item id")
        # Every name and alias must point at exactly one item, or lookups become ambiguous.
        _require_unique(
            (normalize_name(n) for i in self.items for n in (i.name, *i.aliases)),
            "name or alias used more than once",
        )
        return self

    def item(self, item_id: str) -> MenuItem | None:
        return next((i for i in self.items if i.id == item_id), None)


def normalize_name(text: str) -> str:
    return " ".join(text.casefold().split())


def _require_unique(values: Iterable[str], message: str) -> None:
    dupes = sorted(v for v, n in Counter(values).items() if n > 1)
    if dupes:
        raise ValueError(f"{message}: {', '.join(dupes)}")
