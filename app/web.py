"""FastAPI routes: date/level/source listing, paginated/tail reads, search,
export, status, and runtime settings. All backed by TimescaleDB via
asyncpg -- no other storage."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .db import get_pool
from .fetcher import fetcher
from .log_catalog import CATALOG
from .runtime_settings import ValidationError, get_settings, update_settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _filters(day: str | None, search: str | None, level: str | None, source: str | None):
    clauses = []
    params: list = []

    def add(clause: str, value) -> None:
        params.append(value)
        clauses.append(clause.format(n=len(params)))

    if day:
        add("ts::date = ${n}::date", day)
    if search:
        add("raw ILIKE ${n}", f"%{search}%")
    if level:
        add("level = ${n}", level)
    if source:
        add("source = ${n}", source)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/api/dates")
async def api_dates(source: str | None = None):
    pool = get_pool()
    where, params = _filters(None, None, None, source)
    rows = await pool.fetch(
        f"SELECT DISTINCT ts::date AS d FROM log_lines {where} ORDER BY d DESC", *params
    )
    return {"dates": [r["d"].isoformat() for r in rows]}


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
    day: str | None = None,
    search: str | None = None,
    level: str | None = None,
    source: str | None = None,
    offset: int = 0,
    limit: int = Query(default=500, le=5000),
    tail: bool = False,
):
    pool = get_pool()
    where, params = _filters(day, search, level, source)

    total = await pool.fetchval(f"SELECT count(*) FROM log_lines {where}", *params)

    if tail:
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, source, raw FROM log_lines {where} "
            f"ORDER BY ts DESC, id DESC LIMIT ${len(params) + 1}",
            *params, limit,
        )
        rows = list(reversed(rows))
        offset = max(total - len(rows), 0)
    else:
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, source, raw FROM log_lines {where} "
            f"ORDER BY ts, id LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, limit, offset,
        )

    return {
        "total": total,
        "offset": offset,
        "lines": [
            {"id": r["id"], "ts": r["ts"].isoformat(), "level": r["level"],
             "logger": r["logger_name"], "source": r["source"], "raw": r["raw"]}
            for r in rows
        ],
    }


@router.get("/api/logs/export")
async def api_export(
    day: str | None = None,
    search: str | None = None,
    level: str | None = None,
    source: str | None = None,
    start: int = 0,
    end: int | None = None,
):
    pool = get_pool()
    where, params = _filters(day, search, level, source)
    rows = await pool.fetch(f"SELECT raw FROM log_lines {where} ORDER BY ts, id", *params)
    snippet = rows[start:end] if end is not None else rows[start:]
    body = "\n".join(r["raw"] for r in snippet) + ("\n" if snippet else "")
    filename = f"openwb-{source or 'all'}-{day or 'export'}.log"
    return PlainTextResponse(
        body, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/status")
async def api_status():
    pool = get_pool()
    stats = await pool.fetchrow(
        "SELECT count(*) AS total, min(ts) AS oldest, max(ts) AS newest FROM log_lines"
    )
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
                "last_error": st.last_error,
            }
            for name, st in s.sources.items()
        },
        "fetch_interval_seconds": rt["fetch_interval_seconds"],
        "retention_days": rt["retention_days"],
        "source_url": f"{rt['openwb_base_url']}{rt['openwb_ramdisk_path']}",
        "total_rows": stats["total"],
        "oldest": stats["oldest"].isoformat() if stats["oldest"] else None,
        "newest": stats["newest"].isoformat() if stats["newest"] else None,
    }


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
