# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
No formal releases yet — entries are grouped by what shipped, not by tag.

## [Unreleased]

### Fixed
- `GET /api/logs` (and `/api/logs/export`) 500ing whenever a `day` filter
  was passed (including the normal "Heute (live)" view): the SQL cast the
  bound parameter itself (`ts::date = $1::date`), so Postgres reported its
  type as `date` to asyncpg, which then rejected the raw query-string
  `str` FastAPI was handing it. Query params are now typed `date` so
  FastAPI parses them before they ever reach asyncpg.
- "älter"/"neuer" paging did nothing while viewing "Heute (live)": `load()`
  always re-ran the tail query and ignored `offset` in that mode. Paging
  now drops out of live-follow (unchecking "Live") and pages from wherever
  the tail view left off, instead of silently no-op'ing.

### Added
- "Zeilen pro Seite" setting in the settings panel (default raised from a
  hardcoded 1000 to 5000, adjustable 100-20000) — controls the page size
  for both "Heute (live)" tail mode and normal day paging.
- "Zeitraum" from/to datetime picker in the header, as an alternative to
  the day dropdown, for viewing an arbitrary time window instead of a
  whole calendar day — backed by new `from`/`to` filters on `/api/logs`
  and `/api/logs/export` (`ts >= ` / `ts < `, independent of the existing
  `day` equality filter). Fetches the whole selected window in one request
  (up to 20000 lines, `/api/logs`'s own cap raised to match) instead of
  paging 1000 at a time — you already bounded it by picking from/to, so
  paging through it in 1000-line chunks defeated the point. Past that cap
  the view shows only the earliest 20000 lines plus a notice to narrow the
  range further.
- Newest-first display toggle (the ⇅ button next to "Exportieren"),
  remembered in `localStorage`. Purely a display-order flip on already-
  fetched lines; doesn't change what's fetched or how paging works.
- Optional in-app self-update: an "Update" button in the settings panel
  (`POST /api/update`) runs `git pull` then rebuilds and recreates the
  stack via a detached sibling container over the Docker socket. Off by
  default — needs `HOST_REPO_DIR` in `.env` plus starting with
  `-f docker-compose.selfupdate.yml`, since it requires mounting the
  Docker socket into the app container. See `DEPLOYMENT.md`.
- Backfill on first-ever fetch: when a source has no saved tail state yet
  (fresh deployment, or a source just enabled in the settings panel), the
  fetcher now reads its existing rotated backups (oldest first) before the
  current file, instead of only capturing lines going forward. Previously
  whatever history openWB already had on disk at that point was silently
  skipped.
- Multi-source log collection: any of openWB's ramdisk logs (`chargelog`,
  `mqtt`, `smarthome`, `soc`, `internal_chargepoint`, `garbage_collector`,
  `tracemalloc`), not just `main.log`, can be enabled — each parsed with
  the correct format (`DETAILED` vs `SHORT`) per `app/log_catalog.py`.
- All of the tool's own settings (openWB location, enabled log sources,
  retention, poll interval) stored in the database and changeable from a
  settings panel in the UI — no restart required, no environment
  variables at all for these (see "Changed" below).
- Manual "Jetzt abrufen" (fetch now) button in the UI, alongside the
  existing last-fetch timestamp in the status bar, to trigger an
  immediate poll without waiting for the scheduled interval.
- Light/dark/system theme toggle in the UI.
- Source filter alongside the existing day/level/search filters.
- UI fully translated to German.
- `DEVELOPMENT.md`, `DEPLOYMENT.md`, `ROADMAP.md`, `CHANGELOG.md` split out
  of `README.md`.
- Roadmap items: an all-in-one image bundling the app with its database,
  and an MCP server to query collected logs from an AI assistant.

### Changed
- `log_lines` gained a `source` column (default `'main'` for existing
  rows); the retention policy is now re-applied every poll cycle so a
  changed retention setting takes effect without a restart.
- Removed `OPENWB_BASE_URL`, `OPENWB_LOG_PATH`/`OPENWB_RAMDISK_PATH`,
  `OPENWB_BACKUP_COUNT`, `FETCH_INTERVAL_SECONDS`, `RETENTION_DAYS`,
  `HTTP_TIMEOUT_SECONDS`, and `TAIL_WINDOW` as environment variables.
  These are all either configured from the settings panel now (with
  hardcoded fallback defaults on first boot) or, for the last two, plain
  internal constants — not something a user needs to tune. `.env` is now
  just `POSTGRES_PASSWORD` and `PORT`. This was done specifically to
  support bundling the app and database into a single image later, with
  nothing left to configure via env before first start.
- `Fetcher.fetch_once()` is now guarded by a lock so a manual fetch can't
  race the scheduled poll (or another manual click) on the same source's
  tail state.

### Fixed
- `PORT` was read into `Settings.port` but never actually passed to
  uvicorn (the Dockerfile hardcoded `--port 8080`) -- setting a custom
  `PORT` silently did nothing. The Dockerfile's `CMD` now reads `$PORT` at
  container start, and the unused `Settings.port` field was removed.

## [0.1.0] - 2026-08-20

### Added
- Initial version: poll openWB's `main.log` over HTTP on an interval.
- Gap-free merge between polls, with automatic recovery from openWB's own
  rotated backups (`main.log.1`-`.4`) when a rotation happens mid-interval.
- Parse each line into structured fields (timestamp, logger, level,
  thread, message) and store in a TimescaleDB hypertable.
- Retention enforced via a native TimescaleDB retention policy.
- Server-rendered web UI: browse by day, live-tail today, filter by level,
  search, export a line range as a plain-text snippet.
- Docker Compose deployment (app + TimescaleDB), `README.md`, `CLAUDE.md`.
