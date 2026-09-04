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

# Reconstructs the exact original log line from its already-parsed columns,
# instead of also storing it verbatim as a `raw` column would -- for a
# DETAILED-format line, `raw` duplicated the ts/logger_name/line_no/level/
# thread text that's already sitting right next to it in structured form
# (roughly 40% of that column's bytes on this project's own data). Verified
# byte-for-byte against a real Postgres instance (log_lines_fmt_ts's format
# codes, zero-padding, DETAILED/SHORT/continuation cases) before landing
# this. Shared by the trigram index below and by web.py/mcp_server.py's
# queries, so search and display/export always see the identical
# reconstruction.
#
# Uses a small IMMUTABLE wrapper (see _SCHEMA_STATEMENTS) around to_char
# instead of calling it directly: plain to_char() is only STABLE, not
# IMMUTABLE (some of its format codes, e.g. month/day names, depend on
# lc_time), which Postgres rejects in an expression index ("functions in
# index expression must be marked IMMUTABLE") even though the numeric-only
# codes used here (YYYY-MM-DD HH24:MI:SS, MS) never actually vary by
# locale -- verified this restriction is real, not theoretical, since the
# first version of this without the wrapper failed outright at CREATE
# INDEX time.
RAW_EXPR = """(CASE
    WHEN is_continuation THEN message
    WHEN logger_name IS NULL THEN
        log_lines_fmt_ts(ts) || ' - ' || message
    ELSE
        log_lines_fmt_ts(ts) || ' - {' ||
        logger_name || ':' || line_no || '} - {' || level || ':' || thread || '} - ' || message
END)"""

_SCHEMA_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb;",
    # pg_trgm backs idx_log_lines_raw_trgm below, for `raw ILIKE` search --
    # without it, ILIKE over a large log_lines is a full-text sequential scan.
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
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
        is_continuation BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (id, ts)
    );
    """,
    # Additive migration for deployments created before `source` existed.
    "ALTER TABLE log_lines ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'main';",
    # `raw` used to be stored verbatim; now reconstructed on read via
    # RAW_EXPR above (see idx_log_lines_raw_trgm below), so it's redundant.
    "ALTER TABLE log_lines DROP COLUMN IF EXISTS raw;",
    # IMMUTABLE wrapper around to_char so RAW_EXPR is usable in an
    # expression index -- see the comment on RAW_EXPR above for why plain
    # to_char() doesn't qualify.
    """
    CREATE OR REPLACE FUNCTION log_lines_fmt_ts(t TIMESTAMP) RETURNS TEXT AS $$
        SELECT to_char(t, 'YYYY-MM-DD HH24:MI:SS') || ',' || to_char(t, 'MS')
    $$ LANGUAGE SQL IMMUTABLE;
    """,
    "SELECT create_hypertable('log_lines', 'ts', if_not_exists => TRUE);",
    # Default chunk interval is 7 days; with a 7-day chunk size, retention
    # can only ever drop a chunk once it's *entirely* past the cutoff (it
    # can't partially trim a chunk still being written to) -- so 7-day
    # chunks + 7-day retention meant always carrying somewhere between 7
    # and ~14 days of data in a sawtooth, not a clean 7. 1-day chunks let
    # retention track the configured setting much more closely. Only
    # affects chunks created from here on; existing larger chunks keep
    # their original size until retention ages them out naturally.
    "SELECT set_chunk_time_interval('log_lines', INTERVAL '1 day');",
    "CREATE INDEX IF NOT EXISTS idx_log_lines_level ON log_lines (level);",
    # No standalone single-column source index: idx_log_lines_source_ts
    # below (source, ts DESC) already covers a plain `WHERE source = X`
    # via its leading column just as well (standard Postgres behavior for
    # composite indexes), so a separate index here was pure redundancy --
    # measured at ~104 MB on a real instance for zero functional benefit.
    "DROP INDEX IF EXISTS idx_log_lines_source;",
    # Covers the common "filter by source, latest first" shape (tail mode,
    # /api/dates, /api/levels when a source is selected) better than the
    # single-column source index above.
    "CREATE INDEX IF NOT EXISTS idx_log_lines_source_ts ON log_lines (source, ts DESC);",
    # Backs the (ts, id) keyset/cursor pagination in web.py's /api/logs --
    # the table's PK is (id, ts), which doesn't help ORDER BY ts, id or the
    # (ts, id) > (...) row comparisons used there.
    "CREATE INDEX IF NOT EXISTS idx_log_lines_ts_id ON log_lines (ts, id);",
    # GIN trigram index on the *reconstructed* line (RAW_EXPR), not a stored
    # column, so `raw ILIKE '%term%'` (search) can still use an index scan --
    # see CREATE EXTENSION pg_trgm above.
    f"CREATE INDEX IF NOT EXISTS idx_log_lines_raw_trgm "
    f"ON log_lines USING GIN (({RAW_EXPR}) gin_trgm_ops);",
    # Native compression for older chunks: on a real 15M-row instance, this
    # single GIN trigram index alone measured 3.65 GB -- bigger than the
    # actual log data (4.24 GB) -- and compression typically shrinks
    # repetitive text like this 10-20x. Real trade-off, gone into with
    # eyes open: compressed chunks don't maintain btree/GIN indexes the
    # normal way, so ILIKE search reaching into compressed (>1 day old)
    # data falls back to a slower decompress-and-scan path instead of an
    # index scan -- browsing/filtering by day/level/source stays fast
    # either way (TimescaleDB's compression is specifically optimized for
    # that access pattern via compress_orderby/segmentby below). The
    # actively-written chunk (<1 day old) stays uncompressed, so live-tail
    # and recent search are unaffected. segmentby=source since that's the
    # one column always used as an equality filter; orderby matches the
    # (ts, id) keyset pagination order.
    # Guarded, not a bare ALTER: re-running this after chunks already exist
    # fails on some TimescaleDB versions with "cannot change configuration
    # on already compressed chunks" (a real, documented issue in a sibling
    # project's own store -- checked their code specifically for this).
    # Hasn't bitten this project's own TimescaleDB version so far, but this
    # statement runs unconditionally on every single startup, so it's
    # worth not depending on that continuing to be true.
    """
    DO $do$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'log_lines' AND compression_enabled
        ) THEN
            EXECUTE $exec$ALTER TABLE log_lines SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'source',
                timescaledb.compress_orderby = 'ts DESC, id DESC'
            )$exec$;
        END IF;
    END $do$;
    """,
    "SELECT add_compression_policy('log_lines', INTERVAL '1 day', if_not_exists => TRUE);",
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
