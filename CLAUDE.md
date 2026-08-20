# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A small Docker tool that polls openWB's `main.log` (ramdisk, HTTP, rotated
at 5MB / 4 backups) on an interval, merges it gap-free, parses each line,
and stores it in TimescaleDB so the ~1 hour of detail openWB keeps becomes a
full retained history. Includes a small server-rendered web UI to browse,
live-tail, search, and export it. Full picture in `README.md`.

## Architecture

- `app/config.py` — all configuration, read once from env vars at import
  time (`Settings` instance). No other module reads `os.environ` directly.
- `app/log_merge.py` — **pure** functions (no I/O) that find the overlap
  between the previously-seen tail of lines and freshly fetched content, and
  reconstruct lines lost to a rotation from backup files. Unit tested in
  `tests/test_log_merge.py`.
- `app/log_parse.py` — **pure** function parsing one raw log line into a
  structured dict (openWB's `DETAILED` format). Unit tested in
  `tests/test_log_parse.py`.
- `app/db.py` — asyncpg pool, idempotent schema bootstrap (no migration
  tool — the schema is intentionally small), TimescaleDB retention policy,
  and a tiny `fetcher_state` key/value store (replaces any on-disk state
  file; the app container is stateless).
- `app/fetcher.py` — orchestrates: fetch over HTTP -> merge/gap-detect
  (`log_merge`) -> parse (`log_parse`) -> bulk insert. Runs as a background
  `asyncio` task started in `app/main.py`'s lifespan.
- `app/web.py` — FastAPI routes; all reads are plain parameterized SQL via
  asyncpg, no ORM.
- `app/templates/index.html` — the entire frontend: vanilla JS, no build
  step, polls the JSON API.

Storage is TimescaleDB only — there is deliberately no flat-file log output.
Retention is a database policy (`add_retention_policy`), not application
code.

## Commands

```bash
# tests (pure logic only, no DB/network required)
pytest

# local dev: DB via docker, app via uvicorn with reload
docker compose up -d timescaledb
export DATABASE_URL=postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger
uvicorn app.main:app --reload --port 8080

# full stack
docker compose up -d --build
```

## Conventions

- Keep `log_merge.py` and `log_parse.py` free of any I/O (no httpx, no
  asyncpg) — that's what makes them cheap to unit test. New parsing/merging
  logic belongs there; orchestration (HTTP calls, DB writes) belongs in
  `fetcher.py`.
- Timestamps are naive `datetime` throughout (openWB's own wall-clock time,
  no timezone conversion) and the DB column is `TIMESTAMP`, not
  `TIMESTAMPTZ`. Don't introduce timezone-aware datetimes without also
  updating the schema and every comparison point.
- SQL in `web.py`/`db.py` is always parameterized (`$1`, `$2`, ...) — never
  interpolate user input (search terms, day, level) into a query string.
- Line length is 100 cols (`setup.cfg` / `pyproject.toml`), not the flake8
  default of 79.
