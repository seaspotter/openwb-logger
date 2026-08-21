# Development

## Branching

- `main` — stable, releasable. Nothing lands here directly.
- `dev` — active development. Day-to-day work and commits happen here.

When `dev` is in good shape, merge it into `main` (PR or fast-forward
merge) and tag a release there — see `CHANGELOG.md` for what's shipped
since the last one. `main` is what `DEPLOYMENT.md`'s `git clone` /
`git pull` instructions assume.

## Versioning and releasing

[Semantic versioning](https://semver.org/): tags on `main` are
`vMAJOR.MINOR.PATCH`. Given this is a self-contained Docker app (no
public API/library surface), the practical reading is:

- **PATCH** — bug fixes, no settings/behavior removed or changed shape.
- **MINOR** — new features, new settings, anything additive.
- **MAJOR** — anything that isn't a drop-in upgrade: a removed/renamed
  setting, a schema change without an automatic migration path, a
  required manual step (like the pg16→pg18 volume rename in
  `DEPLOYMENT.md`, which *would* have warranted a major bump had this
  project already been past `1.0.0` when it landed).

Staying on `0.x.y` for now (starting at `0.1.0`) — normal for early days,
and honest about the fact that nothing here is a stable, load-bearing
interface yet.

To cut a release:

1. On `dev`, rename `CHANGELOG.md`'s `## [Unreleased]` section to
   `## [X.Y.Z] - YYYY-MM-DD` and start a fresh empty `[Unreleased]` above
   it.
2. Merge `dev` into `main`.
3. `git tag vX.Y.Z && git push origin main --tags`.

That last push is what actually triggers
`.github/workflows/docker-publish.yml` to build and publish the
multi-arch image — see `DEPLOYMENT.md`.

## Setup

Requires Python 3.12+ and a local TimescaleDB (easiest via Docker).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# start just the database
docker compose up -d timescaledb

export DATABASE_URL=postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger

uvicorn app.main:app --reload --port 8080
```

Then open http://localhost:8080 and set your openWB's address from the
settings panel (gear icon) — there's no env var for it. The tool's own
configuration is deliberately not environment-driven (see `app/config.py`
and `app/runtime_settings.py` for why); `DATABASE_URL` and `PORT` are the
only exceptions, since those are infra wiring the app needs before it can
even read its own settings from the database. Hardcoded fallback defaults
(`DEFAULT_OPENWB_BASE_URL` etc. in `app/runtime_settings.py`) are only used
to seed the `app_settings` row on first boot. To reset back to those
defaults during development, drop the row: `DELETE FROM app_settings;`.

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
| `app/config.py` | Infra-level config (DB URL, port) — env vars, fixed per process |
| `app/runtime_settings.py` | All the tool's own settings (openWB location, sources, retention, interval) — stored in DB, editable via UI, no env vars |
| `app/log_catalog.py` | Static catalog of openWB's ramdisk logs (filename, format, backup depth) |
| `app/log_parse.py` | Pure: one raw line -> structured fields |
| `app/log_merge.py` | Pure: overlap/gap detection between polls, backup recovery |
| `app/db.py` | asyncpg pool, schema bootstrap, generic key/value store, retention policy |
| `app/fetcher.py` | Orchestrates fetch -> merge -> parse -> insert per source; lock-guarded so the scheduled poll and a manual "Jetzt abrufen" click can't race |
| `app/web.py` | FastAPI routes (all reads/writes are plain parameterized SQL) |
| `app/templates/index.html` | The entire frontend (German UI) — vanilla JS, no build step |

## Adding a new log source

openWB's other ramdisk logs (`chargelog`, `mqtt`, `soc`,
`internal_chargepoint`, `forecast`) are already in the catalog and can be
enabled from the settings panel without any code change. `forecast` is
speculative — taken from an open, unmerged openWB PR; correct or remove
it once that lands for real. To add one openWB introduces later:

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
