import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from voice_order.store.base import InMemoryOrderStore, OrderStore
from voice_order.store.postgres import PostgresOrderStore

TEST_PREFIX = "test-"  # every session id written by these tests starts with this


def database_url() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL is not set (make test-integration loads it from .env)")
    return dsn


async def open_postgres() -> PostgresOrderStore:
    try:
        return await PostgresOrderStore.connect(database_url(), connect_timeout=3)
    except (PoolTimeout, psycopg.OperationalError) as exc:
        pytest.skip(f"Postgres is not reachable ({exc}); is `make up` running?")


async def delete_test_rows() -> None:
    async with await psycopg.AsyncConnection.connect(database_url()) as conn:
        await conn.execute("DELETE FROM orders WHERE session_id LIKE %s", (f"{TEST_PREFIX}%",))


@pytest.fixture
async def pg_store() -> AsyncIterator[PostgresOrderStore]:
    async with await open_postgres() as store:
        yield store
    await delete_test_rows()


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.integration)])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[OrderStore]:
    """Each contract test runs once per implementation."""
    if request.param == "memory":
        yield InMemoryOrderStore()
        return
    async with await open_postgres() as pg:
        yield pg
    await delete_test_rows()
