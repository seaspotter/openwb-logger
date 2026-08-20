# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
No formal releases yet — entries are grouped by what shipped, not by tag.

## [Unreleased]

### Added
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
