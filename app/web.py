"""FastAPI routes: date/level/source listing, paginated/tail reads, search,
export, status, and runtime settings. All backed by TimescaleDB via
asyncpg -- no other storage."""
from __future__ import annotations

import gzip
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .db import RAW_EXPR, get_pool
from .fetcher import fetcher
from .log_catalog import CATALOG
from .runtime_settings import ValidationError, get_settings, update_settings
from .updater import check_for_update, get_current_version, run_update, self_update_available

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _filters(
    day: date | None,
    search: str | None,
    level: str | None,
    source: str | None,
    from_: datetime | None = None,
    to: datetime | None = None,
    after: tuple[datetime, int] | None = None,
    before: tuple[datetime, int] | None = None,
):
    clauses = []
    params: list = []

    def add(clause: str, *values) -> None:
        # Manual "{}" substitution rather than str.format(): RAW_EXPR (used
        # below for the search clause) contains literal, non-adjacent { }
        # characters of its own (reconstructing openWB's "{logger:lineno}"
        # format), which .format() would misparse as extra replacement
        # fields. Splitting on the literal two-char "{}" marker instead
        # only ever matches an intentional placeholder, never those.
        start = len(params) + 1
        params.extend(values)
        placeholders = [f"${i}" for i in range(start, len(params) + 1)]
        parts = clause.split("{}")
        assert len(parts) == len(placeholders) + 1, \
            f"clause has wrong number of {{}} markers: {clause!r}"
        result = parts[0]
        for part, placeholder in zip(parts[1:], placeholders):
            result += placeholder + part
        clauses.append(result)

    if day:
        add("ts::date = {}::date", day)
    if from_:
        add("ts >= {}", from_)
    if to:
        add("ts < {}", to)
    if after:
        add("(ts, id) > ({}, {})", *after)
    if before:
        add("(ts, id) < ({}, {})", *before)
    if search:
        add(f"{RAW_EXPR} ILIKE {{}}", f"%{search}%")
    if level:
        add("level = {}", level)
    if source:
        add("source = {}", source)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/api/dates")
async def api_dates(source: str | None = None):
    """Every calendar day between the oldest and newest retained line for
    the dropdown, generated from a cheap min/max(ts) lookup instead of
    `SELECT DISTINCT ts::date FROM log_lines` -- at millions of rows that
    scans close to the entire table just to find a handful of distinct
    days, since `ts::date` is a computed expression that (unlike a plain
    indexed column, e.g. /api/levels' `level`) TimescaleDB's SkipScan
    optimization can't apply to; measured at 22s against a real 15M-row
    table before landing this fix. Assumes continuous day-to-day coverage
    (true for an always-on poller) -- a day with genuinely zero rows just
    shows "keine Zeilen" if picked, a fine trade for never scanning the
    table just to build this list."""
    pool = get_pool()
    where, params = _filters(None, None, None, source)
    stats = await pool.fetchrow(
        f"SELECT min(ts) AS oldest, max(ts) AS newest FROM log_lines {where}", *params
    )
    if not stats["oldest"]:
        return {"dates": []}
    dates = []
    d = stats["newest"].date()
    oldest = stats["oldest"].date()
    while d >= oldest:
        dates.append(d.isoformat())
        d -= timedelta(days=1)
    return {"dates": dates}


@router.get("/api/levels")
async def api_levels(source: str | None = None):
    pool = get_pool()
    where, params = _filters(None, None, None, source)
    connector = "AND" if where else "WHERE"
    rows = await pool.fetch(
        f"SELECT DISTINCT level FROM log_lines {where} {connector} level IS NOT NULL "
        f"ORDER BY level",
        *params,
    )
    return {"levels": [r["level"] for r in rows]}


@router.get("/api/sources")
async def api_sources():
    pool = get_pool()
    rt = await get_settings(pool)
    return {
        "enabled": rt["enabled_sources"],
        "catalog": [
            {"name": name, "label": meta["label"], "format": meta["format"]}
            for name, meta in CATALOG.items()
        ],
    }


@router.get("/api/logs")
async def api_logs(
    day: date | None = None,
    search: str | None = None,
    level: str | None = None,
    source: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    after_ts: datetime | None = None,
    after_id: int | None = None,
    before_ts: datetime | None = None,
    before_id: int | None = None,
    limit: int = Query(default=500, le=100000),
    tail: bool = False,
):
    """Keyset (cursor) pagination by (ts, id) instead of OFFSET/LIMIT, so
    paging cost doesn't grow with how deep into a filtered result set you
    are (OFFSET makes Postgres scan and discard every prior row -- see
    ROADMAP.md). `has_more_before`/`has_more_after` replace the old
    `total`/`offset`: fetching `limit + 1` rows reveals whether there's
    more in the direction being paged; the *other* direction is a cheap
    indexed EXISTS check. No COUNT anywhere in this endpoint."""
    pool = get_pool()
    after = (after_ts, after_id) if after_ts is not None and after_id is not None else None
    before = (before_ts, before_id) if before_ts is not None and before_id is not None else None

    async def _exists_beyond(**cursor) -> bool:
        w, p = _filters(day, search, level, source, from_, to, **cursor)
        return await pool.fetchval(f"SELECT EXISTS(SELECT 1 FROM log_lines {w})", *p)

    if tail:
        where, params = _filters(day, search, level, source, from_, to)
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, source, {RAW_EXPR} AS raw FROM log_lines {where} "
            f"ORDER BY ts DESC, id DESC LIMIT ${len(params) + 1}",
            *params, limit + 1,
        )
        has_more_before = len(rows) > limit
        rows = list(reversed(rows[:limit]))
        has_more_after = False
    elif before:
        where, params = _filters(day, search, level, source, from_, to, before=before)
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, source, {RAW_EXPR} AS raw FROM log_lines {where} "
            f"ORDER BY ts DESC, id DESC LIMIT ${len(params) + 1}",
            *params, limit + 1,
        )
        has_more_before = len(rows) > limit
        rows = list(reversed(rows[:limit]))
        has_more_after = bool(rows) and await _exists_beyond(after=(rows[-1]["ts"], rows[-1]["id"]))
    elif after:
        where, params = _filters(day, search, level, source, from_, to, after=after)
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, source, {RAW_EXPR} AS raw FROM log_lines {where} "
            f"ORDER BY ts, id LIMIT ${len(params) + 1}",
            *params, limit + 1,
        )
        has_more_after = len(rows) > limit
        rows = rows[:limit]
        has_more_before = bool(rows) and await _exists_beyond(before=(rows[0]["ts"], rows[0]["id"]))
    else:
        where, params = _filters(day, search, level, source, from_, to)
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, source, {RAW_EXPR} AS raw FROM log_lines {where} "
            f"ORDER BY ts, id LIMIT ${len(params) + 1}",
            *params, limit + 1,
        )
        has_more_after = len(rows) > limit
        rows = rows[:limit]
        has_more_before = False

    return {
        "has_more_before": has_more_before,
        "has_more_after": has_more_after,
        "lines": [
            {"id": r["id"], "ts": r["ts"].isoformat(), "level": r["level"],
             "logger": r["logger_name"], "source": r["source"], "raw": r["raw"]}
            for r in rows
        ],
    }


def _export_filename(source: str | None, day: date | None) -> str:
    return f"openwb-{source or 'all'}-{day or 'export'}.log"


async def _export_body(pool, day, search, level, source, from_, to) -> str:
    """Everything matching the current filter, gap-free and in order --
    exactly what's described by the active source/day-or-Zeitraum/level/
    search selection, not an arbitrary line-index slice (that concept
    doesn't correspond to anything visible once paging is cursor-based;
    see CHANGELOG)."""
    where, params = _filters(day, search, level, source, from_, to)
    rows = await pool.fetch(
        f"SELECT {RAW_EXPR} AS raw FROM log_lines {where} ORDER BY ts, id", *params
    )
    return "\n".join(r["raw"] for r in rows) + ("\n" if rows else "")


@router.get("/api/logs/export")
async def api_export(
    day: date | None = None,
    search: str | None = None,
    level: str | None = None,
    source: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    gzip_: bool = Query(default=False, alias="gzip"),
):
    """`gzip_` (not `gzip`, to avoid shadowing the `gzip` module import used
    below) opts into a real .gz file the browser saves compressed -- not
    `Content-Encoding: gzip`, which browsers transparently decompress
    before saving, defeating the point of asking for a smaller download."""
    pool = get_pool()
    body = await _export_body(pool, day, search, level, source, from_, to)
    filename = _export_filename(source, day)
    if gzip_:
        return Response(
            gzip.compress(body.encode("utf-8")),
            media_type="application/gzip",
            headers={"Content-Disposition": f'attachment; filename="{filename}.gz"'},
        )
    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/logs/export/paste")
async def api_export_paste(
    day: date | None = None,
    search: str | None = None,
    level: str | None = None,
    source: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
):
    """Uploads the current filter's export to openWB's paste instance
    (https://github.com/lucko/paste, self-hosted) and returns a shareable
    link. Same "only on an explicit button click" rule the paste API's own
    terms require for its official instance -- this endpoint only ever
    runs from the user clicking the button, never automatically.

    Gzips the body first: verified directly against the live instance that
    an uncompressed upload over roughly 5MB (a 15-minute Zeitraum export on
    a verbose source is already there) gets a 502 from its reverse proxy,
    while the exact same content gzip-compressed goes through fine --
    bytebin's own README recommends this regardless of that specific
    limit ("ideally, content should be compressed with GZIP")."""
    pool = get_pool()
    body = await _export_body(pool, day, search, level, source, from_, to)
    if not body:
        raise HTTPException(status_code=400, detail="Keine Zeilen für den aktuellen Filter")

    rt = await get_settings(pool)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                rt["paste_upload_url"],
                content=gzip.compress(body.encode("utf-8")),
                headers={
                    "Content-Type": "text/plain",
                    "Content-Encoding": "gzip",
                    "User-Agent": "openwb-logger (github.com/seaspotter/openwb-logger)",
                },
                timeout=30,
            )
        resp.raise_for_status()
        key = resp.json()["key"]
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Paste-Upload fehlgeschlagen: {exc}")
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=502, detail="Paste-Server hat eine unerwartete Antwort geliefert"
        )

    return {"url": f"{rt['paste_view_url']}{key}"}


@router.post("/api/fetch-now")
async def api_fetch_now():
    pool = get_pool()
    await fetcher.fetch_once(pool)
    return {"ok": True}


@router.get("/api/status")
async def api_status():
    """Polled every 5s by every open tab (see index.html), so this must stay
    cheap regardless of table size. approximate_row_count() uses Timescale's
    chunk statistics instead of a full scan; min(ts)/max(ts) are already
    index-optimized by Postgres (converted to an index scan for the
    endpoint) since ts is the hypertable's time-partitioning column.

    recent_error_lines is bounded to the last hour, so it's a cheap,
    chunk-excluded query regardless of total table size -- unlike the
    other per-source fields here (all just in-memory fetcher state), this
    is the one thing that reflects actual log *content* (ERROR-level
    lines), not fetch/parse health, feeding the header's alerts button."""
    pool = get_pool()
    total = await pool.fetchval("SELECT approximate_row_count('log_lines')")
    stats = await pool.fetchrow("SELECT min(ts) AS oldest, max(ts) AS newest FROM log_lines")
    recent_since = datetime.now() - timedelta(hours=1)
    error_rows = await pool.fetch(
        "SELECT source, count(*) AS n FROM log_lines WHERE level = 'ERROR' AND ts > $1 "
        "GROUP BY source",
        recent_since,
    )
    recent_errors = {r["source"]: r["n"] for r in error_rows}
    rt = await get_settings(pool)
    s = fetcher.status
    return {
        "last_fetch_at": s.last_fetch_at,
        "last_success_at": s.last_success_at,
        "last_error": s.last_error,
        "sources": {
            name: {
                "last_lines_added": st.last_lines_added,
                "total_gaps_detected": st.total_gaps_detected,
                "total_gaps_recovered": st.total_gaps_recovered,
                "format_mismatch_suspected": st.format_mismatch_suspected,
                "last_error": st.last_error,
                "recent_error_lines": recent_errors.get(name, 0),
            }
            for name, st in s.sources.items()
        },
        "fetch_interval_seconds": rt["fetch_interval_seconds"],
        "retention_days": rt["retention_days"],
        "source_url": f"{rt['openwb_base_url']}{rt['openwb_ramdisk_path']}",
        "total_rows": total,
        "oldest": stats["oldest"].isoformat() if stats["oldest"] else None,
        "newest": stats["newest"].isoformat() if stats["newest"] else None,
    }


@router.get("/api/update/version")
def api_update_version():
    """Local-only (no network), cheap enough to call on every settings-panel
    open -- unlike /api/update/check below, which does a git fetch."""
    return {"current_commit": get_current_version(), "available": self_update_available()}


@router.get("/api/update/check")
def api_update_check():
    return check_for_update()


@router.post("/api/update")
def api_update(background_tasks: BackgroundTasks):
    """git pull, then -- unless requirements.txt/Dockerfile changed -- restart
    this process so docker-compose's `restart: unless-stopped` brings it back
    with the freshly pulled code (see app/updater.py). Always 200; the result
    dict's `ok`/`message` fields carry success/failure instead of an HTTP
    error, since a failed pull isn't a request-level problem."""
    return run_update(background_tasks)


@router.get("/api/settings")
async def api_get_settings():
    pool = get_pool()
    rt = await get_settings(pool)
    return {
        "settings": rt,
        "catalog": [
            {"name": name, "label": meta["label"], "format": meta["format"]}
            for name, meta in CATALOG.items()
        ],
    }


@router.put("/api/settings")
async def api_put_settings(patch: dict):
    pool = get_pool()
    try:
        rt = await update_settings(pool, patch)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"settings": rt}
