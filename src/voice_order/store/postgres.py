"""Orders in Postgres: one row per session, with the order itself stored as JSONB."""

from types import TracebackType
from typing import Self

from psycopg import AsyncConnection
from psycopg.rows import TupleRow
from psycopg_pool import AsyncConnectionPool

from voice_order.order.models import Order

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    session_id  text PRIMARY KEY,
    status      text NOT NULL,
    order_json  jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
)
"""

UPSERT = """
INSERT INTO orders (session_id, status, order_json)
VALUES (%s, %s, %s::jsonb)
ON CONFLICT (session_id) DO UPDATE
SET status = EXCLUDED.status, order_json = EXCLUDED.order_json, updated_at = now()
"""

SELECT = "SELECT order_json::text FROM orders WHERE session_id = %s"

Pool = AsyncConnectionPool[AsyncConnection[TupleRow]]


class PostgresOrderStore:
    """Use as `async with await PostgresOrderStore.connect(dsn) as store:`."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str, *, max_size: int = 4, connect_timeout: float = 5.0) -> Self:
        """Open a pool and make sure the table exists. Raises PoolTimeout if unreachable."""
        pool: Pool = AsyncConnectionPool(dsn, min_size=1, max_size=max_size, open=False)
        await pool.open(wait=True, timeout=connect_timeout)
        store = cls(pool)
        try:
            await store.ensure_schema()
        except BaseException:
            await pool.close()
            raise
        return store

    async def ensure_schema(self) -> None:
        """Idempotent; safe to run on every start."""
        async with self._pool.connection() as conn:
            await conn.execute(SCHEMA)

    async def save(self, order: Order) -> None:
        # Parameters are sent separately from the SQL, never formatted into it.
        async with self._pool.connection() as conn:
            await conn.execute(UPSERT, (order.session_id, order.status, order.model_dump_json()))

    async def get(self, session_id: str) -> Order | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(SELECT, (session_id,))
            row = await cursor.fetchone()
        return None if row is None else Order.model_validate_json(row[0])

    async def close(self) -> None:
        await self._pool.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
