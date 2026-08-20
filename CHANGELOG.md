# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
No formal releases yet — entries are grouped by what shipped, not by tag.

## [Unreleased]

### Added
- Multi-source log collection: any of openWB's ramdisk logs (`chargelog`,
  `mqtt`, `smarthome`, `soc`, `internal_chargepoint`, `garbage_collector`,
  `tracemalloc`), not just `main.log`, can be enabled — each parsed with
  the correct format (`DETAILED` vs `SHORT`) per `app/log_catalog.py`.
- Runtime-editable settings (openWB location, enabled log sources,
  retention, poll interval) stored in the database and changeable from a
  settings panel in the UI — no restart required. Env vars now only seed
  the initial defaults.
- Light/dark/system theme toggle in the UI.
- Source filter alongside the existing day/level/search filters.
- `DEVELOPMENT.md`, `DEPLOYMENT.md`, `ROADMAP.md`, `CHANGELOG.md` split out
  of `README.md`.

### Changed
- `log_lines` gained a `source` column (default `'main'` for existing
  rows); the retention policy is now re-applied every poll cycle so a
  changed `RETENTION_DAYS`/settings-panel value takes effect without a
  restart.
- `OPENWB_LOG_PATH` and `OPENWB_BACKUP_COUNT` env vars replaced by
  `OPENWB_RAMDISK_PATH` (rotation depth is now defined per-source in the
  catalog, matching openWB's own logger config, not user-configurable).

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
