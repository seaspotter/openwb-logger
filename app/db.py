"""asyncpg connection pool, schema bootstrap, and a tiny key/value store used
by the fetcher to remember its position between polls (and restarts).

No ORM, no migration tool: the schema is small and stable enough that a
single idempotent bootstrap script is simpler to reason about than adding
Alembic. If the schema grows meaningfully, revisit that.
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
    "SELECT create_hypertable('log_lines', 'ts', if_not_exists => TRUE);",
    "CREATE INDEX IF NOT EXISTS idx_log_lines_level ON log_lines (level);",
    """
    CREATE TABLE IF NOT EXISTS fetcher_state (
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
        # Re-applying the retention policy on every start keeps it in sync
        # with RETENTION_DAYS if the setting changes; if_exists makes the
        # removal a no-op on first run.
        await conn.execute("SELECT remove_retention_policy('log_lines', if_exists => true);")
        await conn.execute(
            "SELECT add_retention_policy('log_lines', make_interval(days => $1));",
            settings.retention_days,
        )
    logger.info("Database ready (retention=%sd)", settings.retention_days)
    return _pool


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised; call init_pool() first")
    return _pool


async def get_state(pool: asyncpg.Pool, key: str, default=None):
    row = await pool.fetchrow("SELECT value FROM fetcher_state WHERE key = $1", key)
    return row["value"] if row else default


async def set_state(pool: asyncpg.Pool, key: str, value) -> None:
    await pool.execute(
        "INSERT INTO fetcher_state (key, value) VALUES ($1, $2) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        key,
        value,
    )
