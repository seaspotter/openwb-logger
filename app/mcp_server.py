"""MCP server exposing the collected logs to AI assistants -- mirrors the
web UI's own search/tail/export, mounted on the same FastAPI app (same
port, same DB pool, same trust model) via MCP's Streamable HTTP transport
at /mcp. See app/main.py for how this gets wired into the app's lifespan
(mounting disables FastMCP's own lifespan; the host app's lifespan has to
enter `mcp.session_manager.run()` instead, or the first request fails).

No new authentication here -- this reaches exactly the same data as the
existing web UI/API, under the same no-auth-by-default, LAN-trust model
documented in DEPLOYMENT.md. Put it behind a reverse proxy along with
everything else if that's ever not enough.
"""
from __future__ import annotations

from datetime import date, datetime

from mcp.server.fastmcp import FastMCP

from .db import RAW_EXPR, get_pool
from .log_catalog import CATALOG
from .runtime_settings import get_settings
from .web import _export_body, _filters

# streamable_http_path="/" so mounting this server's ASGI app at "/mcp" on
# the main FastAPI app (see main.py) puts the actual endpoint at exactly
# /mcp, not /mcp/mcp (FastMCP's own default streamable_http_path is
# already "/mcp", meant for when it's the *only* app being served).
mcp = FastMCP("openwb-logger", streamable_http_path="/")

# Modest limits, unlike the web UI's own (Zeitraum's RANGE_LIMIT=100000,
# sized for what a browser can render): responses here flow into an LLM's
# context window, which has a much tighter, more expensive budget than a
# browser tab.
SEARCH_DEFAULT_LIMIT = 200
SEARCH_MAX_LIMIT = 2000
TAIL_DEFAULT_N = 100
TAIL_MAX_N = 1000


def _rows_to_dicts(rows) -> list[dict]:
    return [
        {
            "id": r["id"], "ts": r["ts"].isoformat(), "level": r["level"],
            "logger": r["logger_name"], "source": r["source"], "raw": r["raw"],
        }
        for r in rows
    ]


@mcp.tool()
async def search_logs(
    day: date | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    level: str | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = SEARCH_DEFAULT_LIMIT,
) -> list[dict]:
    """Search openWB's collected log history. Filter by a specific
    calendar day, an arbitrary from/to timestamp range, log level,
    source (see the openwb://sources resource for valid names), and/or a
    text search term (matches anywhere in the raw line). Returns matching
    lines in chronological order, capped at `limit` (default 200, max
    2000) -- narrow the filters instead of raising this past the cap."""
    pool = get_pool()
    limit = min(limit, SEARCH_MAX_LIMIT)
    where, params = _filters(day, search, level, source, from_, to)
    rows = await pool.fetch(
        f"SELECT id, ts, level, logger_name, source, {RAW_EXPR} AS raw FROM log_lines {where} "
        f"ORDER BY ts, id LIMIT ${len(params) + 1}",
        *params, limit,
    )
    return _rows_to_dicts(rows)


@mcp.tool()
async def tail_logs(
    level: str | None = None,
    source: str | None = None,
    n: int = TAIL_DEFAULT_N,
) -> list[dict]:
    """Returns the `n` most recent log lines (default 100, max 1000),
    optionally filtered by level and/or source, in chronological order
    (oldest of the batch first)."""
    pool = get_pool()
    n = min(n, TAIL_MAX_N)
    where, params = _filters(None, None, level, source)
    rows = await pool.fetch(
        f"SELECT id, ts, level, logger_name, source, {RAW_EXPR} AS raw FROM log_lines {where} "
        f"ORDER BY ts DESC, id DESC LIMIT ${len(params) + 1}",
        *params, n,
    )
    return _rows_to_dicts(list(reversed(rows)))


@mcp.tool()
async def export_logs(
    day: date | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    level: str | None = None,
    source: str | None = None,
    search: str | None = None,
) -> str:
    """Returns every matching line as one plain-text blob (the same query
    the web UI's "Exportieren" button runs), one raw line per line of
    text. No line cap -- narrow the filters (day/range/level/source/
    search) for anything beyond a single day or a bounded time window,
    since an unbounded query can return a very large amount of text."""
    pool = get_pool()
    return await _export_body(pool, day, search, level, source, from_, to)


@mcp.tool()
async def get_storage_info() -> dict:
    """Current storage footprint: total row count, oldest/newest
    timestamp, byte breakdown (table/index/toast/total) of the whole
    `log_lines` hypertable, per-source row counts, and the current
    retention setting. For answering "how much disk is my log data
    using" without hand-writing SQL against the database directly."""
    pool = get_pool()
    rt = await get_settings(pool)
    total_rows = await pool.fetchval("SELECT approximate_row_count('log_lines')")
    stats = await pool.fetchrow("SELECT min(ts) AS oldest, max(ts) AS newest FROM log_lines")
    size = await pool.fetchrow(
        "SELECT table_bytes, index_bytes, toast_bytes, total_bytes "
        "FROM hypertable_detailed_size('log_lines')"
    )
    per_source = await pool.fetch(
        "SELECT source, count(*) AS n FROM log_lines GROUP BY source ORDER BY n DESC"
    )
    return {
        "total_rows": total_rows,
        "oldest": stats["oldest"].isoformat() if stats["oldest"] else None,
        "newest": stats["newest"].isoformat() if stats["newest"] else None,
        "table_bytes": size["table_bytes"],
        "index_bytes": size["index_bytes"],
        "toast_bytes": size["toast_bytes"],
        "total_bytes": size["total_bytes"],
        "retention_days": rt["retention_days"],
        "rows_per_source": {r["source"]: r["n"] for r in per_source},
    }


@mcp.resource("openwb://sources")
def list_sources() -> list[dict]:
    """The known openWB log sources -- valid `source` values for
    search_logs/tail_logs/export_logs, along with each one's log
    format."""
    return [
        {"name": name, "label": meta["label"], "format": meta["format"]}
        for name, meta in CATALOG.items()
    ]
