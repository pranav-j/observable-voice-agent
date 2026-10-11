"""The OrderStore contract. Every implementation must pass all of these."""

from uuid import uuid4

from tests.store.conftest import TEST_PREFIX
from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.store.base import OrderStore


def sid() -> str:
    return f"{TEST_PREFIX}{uuid4().hex}"


async def test_unknown_session_is_none(store: OrderStore) -> None:
    assert await store.get(sid()) is None


async def test_save_then_get_round_trips_everything(store: OrderStore, menu: Menu) -> None:
    order = state.new_order(sid())
    order = state.add_line(order, menu, "cold_coffee", 2, "large", ["oat_milk", "extra_shot"])
    order = state.set_customer(order, "Anil", "9000000001")
    order = state.confirm(state.mark_readback(order))
    await store.save(order)
    assert await store.get(order.session_id) == order


async def test_save_replaces_by_session_id(store: OrderStore, menu: Menu) -> None:
    first = state.new_order(sid())
    await store.save(first)
    second = state.add_line(first, menu, "affogato", 1)
    await store.save(second)
    assert await store.get(first.session_id) == second


async def test_sessions_are_independent(store: OrderStore, menu: Menu) -> None:
    a = state.new_order(sid())
    b = state.add_line(state.new_order(sid()), menu, "affogato", 1)
    await store.save(a)
    await store.save(b)
    assert await store.get(a.session_id) == a
    assert await store.get(b.session_id) == b
