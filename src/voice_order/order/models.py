"""Order models. Validators enforce the invariants however an Order gets built."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_QUANTITY = 20

OrderStatus = Literal["draft", "confirmed", "abandoned", "escalated"]
LineKey = tuple[str, str | None, tuple[str, ...]]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class OrderLine(_Frozen):
    line_id: Annotated[int, Field(ge=1)]
    item_id: str
    size_id: str | None
    modifier_ids: list[str]  # stored sorted, no duplicates
    quantity: Annotated[int, Field(ge=1, le=MAX_QUANTITY)]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.modifier_ids != sorted(set(self.modifier_ids)):
            raise ValueError("modifier_ids must be sorted and unique")
        return self

    @property
    def key(self) -> LineKey:
        """Lines with the same key are the same product and get merged."""
        return (self.item_id, self.size_id, tuple(self.modifier_ids))


class Customer(_Frozen):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    phone: Annotated[str, StringConstraints(pattern=r"^\d{10}$")]


class Order(_Frozen):
    session_id: str
    lines: list[OrderLine] = []
    customer: Customer | None = None
    mutation_seq: Annotated[int, Field(ge=0)] = 0  # bumped on every change to lines or customer
    readback_seq: int | None = None  # mutation_seq when the read-back was last fetched
    status: OrderStatus = "draft"
    next_line_id: Annotated[int, Field(ge=1)] = 1  # line ids are never reused

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [line.line_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate line_id")
        if ids and max(ids) >= self.next_line_id:
            raise ValueError("next_line_id must be greater than every line_id")
        keys = [line.key for line in self.lines]
        if len(keys) != len(set(keys)):
            raise ValueError("two lines for the same item, size and modifiers")
        if self.readback_seq is not None and self.readback_seq > self.mutation_seq:
            raise ValueError("readback_seq is ahead of mutation_seq")
        return self

    @property
    def readback_is_current(self) -> bool:
        return self.readback_seq == self.mutation_seq
