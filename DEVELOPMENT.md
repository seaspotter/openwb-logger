# Development

## Setup

Requires Python 3.12+ and a local TimescaleDB (easiest via Docker).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# start just the database
docker compose up -d timescaledb

export DATABASE_URL=postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger
export OPENWB_BASE_URL=http://10.1.5.32   # or wherever your openWB is

uvicorn app.main:app --reload --port 8080
```

The `OPENWB_*`, `FETCH_INTERVAL_SECONDS`, and `RETENTION_DAYS` env vars are
only the *initial* seed values written to `app_settings` on first boot;
after that, the settings panel in the UI is the source of truth (see
`app/runtime_settings.py`). To reset back to env-var defaults during
development, drop the `app_settings` row: `DELETE FROM app_settings;`.

## Tests

```bash
pytest
```

Everything under `tests/` exercises pure logic only (`log_merge.py`,
`log_parse.py`, `runtime_settings.validate`) — no database or network
required, deliberately, so the suite stays fast. HTTP fetching, DB
inserts, and the retention policy are integration-level concerns better
verified by actually running `docker compose up` against a real (or
staging) openWB.

## Project layout

| Path | Purpose |
|---|---|
| `app/config.py` | Deployment-level config (DB URL, port) — env vars, fixed per process |
| `app/runtime_settings.py` | User-editable settings (openWB location, sources, retention, interval) — stored in DB, editable via UI |
| `app/log_catalog.py` | Static catalog of openWB's ramdisk logs (filename, format, backup depth) |
| `app/log_parse.py` | Pure: one raw line -> structured fields |
| `app/log_merge.py` | Pure: overlap/gap detection between polls, backup recovery |
| `app/db.py` | asyncpg pool, schema bootstrap, generic key/value store, retention policy |
| `app/fetcher.py` | Orchestrates fetch -> merge -> parse -> insert per source |
| `app/web.py` | FastAPI routes (all reads/writes are plain parameterized SQL) |
| `app/templates/index.html` | The entire frontend — vanilla JS, no build step |

## Adding a new log source

openWB's other ramdisk logs (`chargelog`, `mqtt`, `smarthome`, `soc`,
`internal_chargepoint`, `garbage_collector`, `tracemalloc`) are already in
the catalog and can be enabled from the settings panel without any code
change. To add one openWB introduces later:

1. Add an entry to `CATALOG` in `app/log_catalog.py` with its filename
   stem, format (`"detailed"` or `"short"` — check openWB's
   `packages/helpermodules/logger.py`), and rotation depth.
2. That's it — the fetcher, parser, and settings UI all read from the
   catalog dynamically.

## Code style

- Line length is 100 columns (`setup.cfg` / `pyproject.toml`), not the
  flake8 default of 79.
- `log_merge.py`, `log_parse.py`, and `runtime_settings.validate()` must
  stay free of I/O (no httpx, no asyncpg) — that's what makes them cheap
  to unit test. New parsing/merging/validation logic belongs there;
  orchestration (HTTP calls, DB writes) belongs in `fetcher.py` / `web.py`.
- SQL is always parameterized (`$1`, `$2`, ...) — never interpolate
  request input (search terms, day, level, source) into a query string.
