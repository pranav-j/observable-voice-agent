"""The OrderStore interface and an in-memory implementation."""

from typing import Protocol

from voice_order.order.models import Order


class OrderStore(Protocol):
    """Where orders live after a call. One writer per session; no locking."""

    async def save(self, order: Order) -> None:
        """Insert the order, or replace the stored one with the same session_id."""
        ...

    async def get(self, session_id: str) -> Order | None: ...


class InMemoryOrderStore:
    """For unit tests and offline text runs. Orders are immutable, so sharing them is safe."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    async def save(self, order: Order) -> None:
        self._orders[order.session_id] = order

    async def get(self, session_id: str) -> Order | None:
        return self._orders.get(session_id)
