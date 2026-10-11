"""InMemoryOrderStore satisfies the OrderStore contract."""

from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.store.base import InMemoryOrderStore, OrderStore


async def test_unknown_session_is_none() -> None:
    assert await InMemoryOrderStore().get("nope") is None


async def test_save_then_get(menu: Menu) -> None:
    store: OrderStore = InMemoryOrderStore()  # type-checks against the protocol
    order = state.add_line(state.new_order("s1"), menu, "masala_dosa", 2)
    await store.save(order)
    assert await store.get("s1") == order


async def test_save_replaces_by_session_id(menu: Menu) -> None:
    store = InMemoryOrderStore()
    first = state.new_order("s1")
    await store.save(first)
    second = state.add_line(first, menu, "affogato", 1)
    await store.save(second)
    assert await store.get("s1") == second


async def test_sessions_are_independent(menu: Menu) -> None:
    store = InMemoryOrderStore()
    await store.save(state.new_order("a"))
    await store.save(state.add_line(state.new_order("b"), menu, "affogato", 1))
    a, b = await store.get("a"), await store.get("b")
    assert a is not None
    assert b is not None
    assert (len(a.lines), len(b.lines)) == (0, 1)
