# 0002: Order persistence

- **Status:** accepted
- **Date:** 2026-10-11

## Context

Each call's order has to outlive the process that handled the call. The eval harness reads the final order for every scenario run, and the backend serves orders to the web UI. The processes that write orders (the voice worker, the text-mode runner) and the ones that read them (the harness, the API) are separate, and they all run on asyncio.

The order itself is an immutable Pydantic model. Tools never write to storage: each tool call returns a new `Order` and replaces the one held by the session. One session has exactly one writer, the process running that call.

## Decision

- **Database driver:** `psycopg` 3 in async mode, with a small connection pool.
- **Plain SQL, no ORM.** One table:

  ```sql
  CREATE TABLE IF NOT EXISTS orders (
      session_id  text PRIMARY KEY,
      status      text NOT NULL,
      order_json  jsonb NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now(),
      updated_at  timestamptz NOT NULL DEFAULT now()
  );
  ```

  The whole order is stored as JSONB, written with `model_dump_json()` and read back with `model_validate_json()`, so Pydantic stays the single definition of an order's shape. `status` is copied into its own column so the harness and the API can filter on it.
- **Schema setup:** the store runs the idempotent `CREATE TABLE IF NOT EXISTS` when it starts. There is no migration tool yet.
- **Interface:** an `OrderStore` protocol with `save(order)` (insert or update) and `get(session_id)`. There are two implementations: Postgres, and an in-memory store for unit tests and quick local text runs.
- **Who saves:** the runtime, not the tools. After each tool call that produced a new order, the text loop or voice worker calls `save(session.order)`. The core stays free of I/O and the tools stay deterministic.

## Alternatives

- **SQLAlchemy (ORM or Core) or SQLModel.** These are useful once there are many tables and relationships. With one table they add a second model definition that has to stay in sync with the Pydantic one.
- **asyncpg.** It's fast, but it is async-only and has its own API. psycopg 3 supports both sync and async with the same interface, which is convenient for scripts and the harness.
- **Normalized tables** (`orders`, `order_lines`). These would allow SQL queries per line, but nothing needs that. Scoring loads the whole order and compares it in Python.
- **Alembic from day one.** It isn't worth the setup for one table that is created idempotently.

## Consequences

- Adding a field to `Order` with a default needs no database change, because old JSON still validates. Renaming or removing a field means either rewriting stored rows or adding a migration step.
- Alembic gets introduced when a second table or the first non-additive change shows up.
- Queries can't look inside lines efficiently. That's acceptable at this scale, and JSONB operators exist if it's ever needed.
- Unit tests and offline text runs can use the in-memory store and need no Postgres. Integration tests run the same contract against the real database.
- Concurrent writers for the same session are not handled, because there is only ever one per call. If that changes, `save` needs an optimistic check, for example on `mutation_seq` plus `status`.
