"""Postgres-specific behavior beyond the shared contract."""

import psycopg
import pytest

from tests.store.conftest import TEST_PREFIX, database_url
from voice_order.menu.models import Menu
from voice_order.order import state
from voice_order.store.postgres import PostgresOrderStore

pytestmark = pytest.mark.integration


async def row(session_id: str) -> tuple[str, str]:
    async with await psycopg.AsyncConnection.connect(database_url()) as conn:
        cursor = await conn.execute(
            "SELECT status, order_json->>'status' FROM orders WHERE session_id = %s",
            (session_id,),
        )
        result = await cursor.fetchone()
    assert result is not None
    return result[0], result[1]


async def test_status_column_follows_the_order(pg_store: PostgresOrderStore, menu: Menu) -> None:
    order = state.add_line(state.new_order(f"{TEST_PREFIX}status"), menu, "affogato", 1)
    await pg_store.save(order)
    assert await row(order.session_id) == ("draft", "draft")
    await pg_store.save(state.abandon(order))
    assert await row(order.session_id) == ("abandoned", "abandoned")


async def test_schema_setup_is_idempotent(pg_store: PostgresOrderStore) -> None:
    await pg_store.ensure_schema()
    await pg_store.ensure_schema()


async def test_tricky_text_is_stored_safely(pg_store: PostgresOrderStore) -> None:
    sid = f"{TEST_PREFIX}'; DROP TABLE orders; --"
    order = state.set_customer(state.new_order(sid), 'O\'Brien "Bob" ✓', "9000000001")
    await pg_store.save(order)
    assert await pg_store.get(sid) == order
