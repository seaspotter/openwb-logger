"""asyncpg connection pool, schema bootstrap, and small generic key/value
helpers used both for internal fetcher position tracking (`fetcher_state`)
and for user-editable runtime settings (`app_settings`, see
runtime_settings.py).

No ORM, no migration tool: the schema is small and stable enough that a
single idempotent bootstrap script -- CREATE ... IF NOT EXISTS plus additive
ALTER ... ADD COLUMN IF NOT EXISTS for later changes -- is simpler to reason
about than adding Alembic. If the schema grows meaningfully, revisit that.
"""
from __future__ import annotations

import json
import logging

import asyncpg

from .config import settings

logger = logging.getLogger("openwb_logger.db")

_pool: asyncpg.Pool | None = None

_SCHEMA_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb;",
    """
    CREATE TABLE IF NOT EXISTS log_lines (
        id BIGSERIAL NOT NULL,
        -- Naive timestamp, exactly as openWB's asctime writes it (device
        -- wall-clock time, no timezone). See app/log_parse.py.
        ts TIMESTAMP NOT NULL,
        source TEXT NOT NULL DEFAULT 'main',
        logger_name TEXT,
        line_no INTEGER,
        level TEXT,
        thread TEXT,
        message TEXT,
        raw TEXT NOT NULL,
        is_continuation BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (id, ts)
    );
    """,
    # Additive migration for deployments created before `source` existed.
    "ALTER TABLE log_lines ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'main';",
    "SELECT create_hypertable('log_lines', 'ts', if_not_exists => TRUE);",
    "CREATE INDEX IF NOT EXISTS idx_log_lines_level ON log_lines (level);",
    "CREATE INDEX IF NOT EXISTS idx_log_lines_source ON log_lines (source);",
    """
    CREATE TABLE IF NOT EXISTS fetcher_state (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL
    );
    """,
]


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def init_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=5, init=_init_connection
    )
    async with _pool.acquire() as conn:
        for stmt in _SCHEMA_STATEMENTS:
            await conn.execute(stmt)
    logger.info("Database ready")
    return _pool


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised; call init_pool() first")
    return _pool


async def apply_retention_policy(pool: asyncpg.Pool, days: int) -> None:
    """(Re)applies the TimescaleDB retention policy. Safe to call repeatedly
    -- e.g. once at startup and again whenever the setting changes."""
    async with pool.acquire() as conn:
        await conn.execute("SELECT remove_retention_policy('log_lines', if_exists => true);")
        await conn.execute(
            "SELECT add_retention_policy('log_lines', make_interval(days => $1));", days
        )


async def get_kv(pool: asyncpg.Pool, table: str, key: str, default=None):
    row = await pool.fetchrow(f"SELECT value FROM {table} WHERE key = $1", key)
    return row["value"] if row else default


async def set_kv(pool: asyncpg.Pool, table: str, key: str, value) -> None:
    await pool.execute(
        f"INSERT INTO {table} (key, value) VALUES ($1, $2) "
        f"ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        key,
        value,
    )


async def get_state(pool: asyncpg.Pool, key: str, default=None):
    return await get_kv(pool, "fetcher_state", key, default)


async def set_state(pool: asyncpg.Pool, key: str, value) -> None:
    await set_kv(pool, "fetcher_state", key, value)
