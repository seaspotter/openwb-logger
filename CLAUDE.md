# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A small Docker tool that polls openWB's ramdisk logs (`main.log` by
default, optionally others — HTTP, each rotated per openWB's own config)
on an interval, merges them gap-free, parses each line, and stores it in
TimescaleDB so the ~1 hour of detail openWB keeps becomes a full retained
history. Includes a small server-rendered web UI (German, light/dark) to
browse, live-tail, search, export it, and trigger an immediate fetch on
demand, plus a settings panel to change where openWB is, which logs to
collect, retention, and poll interval at runtime — no environment
variables, no restart. Full picture in `README.md`; details in
`DEVELOPMENT.md` and `DEPLOYMENT.md`.

## Architecture

- `app/config.py` — **infra-level** config only, read once from env vars
  at import time: `DATABASE_URL` and `PORT`. Nothing about the tool's own
  behavior lives here on purpose (see the module docstring) — that split
  is what makes it possible to eventually bundle the app and its database
  into a single image with essentially nothing left to configure via env.
- `app/runtime_settings.py` — **all** user-editable settings (openWB
  location, enabled log sources, retention, poll interval), stored as one
  JSONB row in `app_settings` and re-read every poll cycle, so changes
  made via the UI take effect without a restart. Hardcoded `DEFAULT_*`
  constants here (not env vars) seed the row on first boot. `validate()`
  is pure — no DB/HTTP — and is what the PUT `/api/settings` endpoint and
  its tests both use.
- `app/log_catalog.py` — static catalog of openWB's known ramdisk logs
  (filename stem, `DETAILED`/`SHORT` format, rotation depth). Fixed by
  openWB itself, not user-editable — see `DEVELOPMENT.md` for how to add a
  new one.
- `app/log_merge.py` — **pure** functions (no I/O) that find the overlap
  between the previously-seen tail of lines and freshly fetched content,
  and reconstruct lines lost to a rotation from backup files. Unit tested.
- `app/log_parse.py` — **pure** function parsing one raw log line into a
  structured dict, dispatching on the source's format (`detailed`/
  `short`). Unit tested.
- `app/db.py` — asyncpg pool, idempotent schema bootstrap (no migration
  tool — additive `ALTER ... ADD COLUMN IF NOT EXISTS` instead), the
  retention-policy helper, and a generic key/value store used by both
  `fetcher_state` (internal poll position, per source) and `app_settings`.
- `app/fetcher.py` — orchestrates, per enabled source: fetch over HTTP ->
  merge/gap-detect (`log_merge`) -> parse (`log_parse`) -> bulk insert.
  Reads runtime settings fresh every cycle and returns them so the poll
  loop in `app/main.py` can sleep for the *current* interval. Runs as a
  background `asyncio` task started in `main.py`'s lifespan.
  `Fetcher._lock` serializes `fetch_once()` calls so the scheduled poll and
  a manual "Jetzt abrufen" (`POST /api/fetch-now`) trigger can't race on
  the same source's tail state.
- `app/web.py` — FastAPI routes; all reads/writes are plain parameterized
  SQL via asyncpg, no ORM.
- `app/templates/index.html` — the entire frontend, **in German**: vanilla
  JS, no build step, polls the JSON API. Theme is CSS custom properties
  (light default, dark via `prefers-color-scheme` and/or a `data-theme`
  override persisted in `localStorage`) — see the design-token block at
  the top of the file. Keep new UI copy in German too.

Storage is TimescaleDB only — there is deliberately no flat-file log
output. Retention is a database policy (`add_retention_policy`), not
application code, re-applied every poll cycle in case the setting changed.

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

- Keep `log_merge.py`, `log_parse.py`, and `runtime_settings.validate()`
  free of any I/O (no httpx, no asyncpg) — that's what makes them cheap to
  unit test. New parsing/merging/validation logic belongs there;
  orchestration (HTTP calls, DB writes) belongs in `fetcher.py` / `web.py`.
- `runtime_settings.ValidationError` messages are user-facing (shown
  directly in the settings panel) and are in German — keep them that way.
- No environment variables for the tool's own behavior — new user-facing
  settings go in `runtime_settings.py`, not `app/config.py`.
- Timestamps are naive `datetime` throughout (openWB's own wall-clock
  time, no timezone conversion) and the DB column is `TIMESTAMP`, not
  `TIMESTAMPTZ`. Don't introduce timezone-aware datetimes without also
  updating the schema and every comparison point.
- SQL in `web.py`/`db.py` is always parameterized (`$1`, `$2`, ...) — never
  interpolate request input (search terms, day, level, source) into a
  query string. Table names in the generic `get_kv`/`set_kv` helpers are
  the one exception — those are always hardcoded literals from our own
  code, never user input.
- Line length is 100 cols (`setup.cfg` / `pyproject.toml`), not the flake8
  default of 79.
- Update `CHANGELOG.md` (Unreleased section) and, if scope changed,
  `ROADMAP.md` when landing a user-visible change.
