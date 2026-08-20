"""FastAPI routes: date/level listing, paginated/tail reads, search, export,
status. All backed by TimescaleDB via asyncpg -- no other storage."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .config import settings
from .db import get_pool
from .fetcher import fetcher

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _filters(day: str | None, search: str | None, level: str | None):
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
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/api/dates")
async def api_dates():
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT ts::date AS d FROM log_lines ORDER BY d DESC"
    )
    return {"dates": [r["d"].isoformat() for r in rows]}


@router.get("/api/levels")
async def api_levels():
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT DISTINCT level FROM log_lines WHERE level IS NOT NULL ORDER BY level"
    )
    return {"levels": [r["level"] for r in rows]}


@router.get("/api/logs")
async def api_logs(
    day: str | None = None,
    search: str | None = None,
    level: str | None = None,
    offset: int = 0,
    limit: int = Query(default=500, le=5000),
    tail: bool = False,
):
    pool = get_pool()
    where, params = _filters(day, search, level)

    total = await pool.fetchval(f"SELECT count(*) FROM log_lines {where}", *params)

    if tail:
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, raw FROM log_lines {where} "
            f"ORDER BY ts DESC, id DESC LIMIT ${len(params) + 1}",
            *params, limit,
        )
        rows = list(reversed(rows))
        offset = max(total - len(rows), 0)
    else:
        rows = await pool.fetch(
            f"SELECT id, ts, level, logger_name, raw FROM log_lines {where} "
            f"ORDER BY ts, id LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, limit, offset,
        )

    return {
        "total": total,
        "offset": offset,
        "lines": [
            {"id": r["id"], "ts": r["ts"].isoformat(), "level": r["level"],
             "logger": r["logger_name"], "raw": r["raw"]}
            for r in rows
        ],
    }


@router.get("/api/logs/export")
async def api_export(
    day: str | None = None,
    search: str | None = None,
    level: str | None = None,
    start: int = 0,
    end: int | None = None,
):
    pool = get_pool()
    where, params = _filters(day, search, level)
    rows = await pool.fetch(
        f"SELECT raw FROM log_lines {where} ORDER BY ts, id", *params
    )
    snippet = rows[start:end] if end is not None else rows[start:]
    body = "\n".join(r["raw"] for r in snippet) + ("\n" if snippet else "")
    filename = f"openwb-{day or 'export'}.log"
    return PlainTextResponse(
        body, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/api/status")
async def api_status():
    pool = get_pool()
    stats = await pool.fetchrow(
        "SELECT count(*) AS total, min(ts) AS oldest, max(ts) AS newest FROM log_lines"
    )
    s = fetcher.status
    return {
        "last_fetch_at": s.last_fetch_at,
        "last_success_at": s.last_success_at,
        "last_error": s.last_error,
        "last_lines_added": s.last_lines_added,
        "total_gaps_detected": s.total_gaps_detected,
        "total_gaps_recovered": s.total_gaps_recovered,
        "fetch_interval_seconds": settings.fetch_interval_seconds,
        "retention_days": settings.retention_days,
        "source": settings.log_url,
        "total_rows": stats["total"],
        "oldest": stats["oldest"].isoformat() if stats["oldest"] else None,
        "newest": stats["newest"].isoformat() if stats["newest"] else None,
    }
