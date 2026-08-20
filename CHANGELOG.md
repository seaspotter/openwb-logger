# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
No formal releases yet — entries are grouped by what shipped, not by tag.

## [Unreleased]

### Fixed
- "An Paste senden" 502ing on uploads over roughly 5MB (a 15-minute
  Zeitraum export on a verbose source is already there) — confirmed
  directly against the live `bytebin.openwb.de` instance that its reverse
  proxy rejects uncompressed bodies past that point. Now gzips before
  uploading (`Content-Encoding: gzip`), which bytebin's own docs recommend
  regardless of that specific limit; the same content that 502'd
  uncompressed went through fine compressed in testing.
- App-generated timestamps (e.g. "Letzter Abruf" in the status bar) showed
  the container's default UTC clock instead of local time, since nothing
  told the container what timezone it was in. New `TZ` env var (defaults
  to `Europe/Berlin`; override in `.env` if that's not your zone) fixes
  it; log lines' own `ts` were never affected (they come straight from
  openWB's log text, not the container's clock).
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
- Theme toggle only visibly changed on the *second* click: it cycled
  system → light → dark → system, and system → light was a silent no-op
  whenever the OS was already in light mode. Now a plain light/dark flip
  (system preference only decides the very first, pre-`localStorage` load).

### Changed
- Replaced native browser `confirm()`/`alert()`/`prompt()` (the update
  button's confirmation, paste-upload errors, and the paste link display)
  with in-app toasts and a modal, matching the pattern already used in
  `knxpilot` — these no longer open as a separate browser-chrome popup.
- Export ("Exportieren") no longer has separate "Zeile von/bis" line-index
  fields — that concept stopped corresponding to anything visible once
  paging became cursor-based, so it was just confusing (which line is
  "0"?). It now always exports exactly the active filter (source/day-or-
  Zeitraum/level/search), same as what's on screen, and is disabled while
  live-following (exporting a constantly-moving target doesn't make
  sense) — pick a day, a Zeitraum, or pause "Live" first.
- Log view is taller: `calc(100vh - 170px)` instead of a fixed `70vh`, so it
  fills the available window space instead of leaving a growing gap on
  tall windows.
- DEBUG-level log lines are now dark green instead of grey.
- "Live" now turns itself off (not just visually inert) when you scroll
  away from the live edge, change the log level, search, or pick a
  Zeitraum range — previously only älter/neuer did this, so those other
  interactions left "Live" checked while an auto-refresh or auto-scroll
  could still pull the view out from under you mid-read.
- Reduced recurring DB load, unrelated to actual usage, that was scaling
  with table size regardless of how many people were looking:
  - `GET /api/status` (polled every 5s by every open tab) no longer runs a
    full `COUNT(*)` — it now uses TimescaleDB's `approximate_row_count()`,
    which reads chunk statistics instead of scanning the table. `min(ts)`/
    `max(ts)` are unaffected (Postgres already turns those into a cheap
    index scan via the hypertable's time index).
  - `GET /api/logs`'s filtered `COUNT(*)` (needed for the tail window's
    starting offset, re-run on every live-tail poll) is gone entirely —
    see the keyset pagination rewrite below, which removed the need for
    any count, cached or not.
  - Added indexes: `(source, ts DESC)` for the common "filter by source,
    latest first" query shape, `(ts, id)` for the keyset pagination below,
    and a `pg_trgm` GIN index on `raw` so search (`ILIKE`) can use an
    index scan instead of reading every row. All built automatically on
    next startup (`CREATE INDEX IF NOT EXISTS`) — on an already-large
    table this can take a while and briefly hold a lock per chunk;
    harmless but worth expecting on the first restart after this update,
    not on every restart after.
- `GET /api/logs` (and the frontend's day/Zeitraum paging) now uses
  cursor/keyset pagination by `(ts, id)` instead of `OFFSET/LIMIT`.
  `OFFSET` makes Postgres scan and discard every prior row, so paging got
  slower the deeper into a busy day/range you went; a cursor comparison
  costs the same regardless of depth. The API's `total`/`offset` response
  fields are gone, replaced by `has_more_before`/`has_more_after` (no
  `COUNT` needed for either — see above) — the log view now shows a plain
  line count instead of "X-Y von Z", and älter/neuer disable themselves
  based on those flags instead of a total.

### Added
- Format-mismatch warning: previously, a source whose actual log format
  no longer matched what `log_catalog.py` declared (e.g. an openWB update
  changing its format) failed completely silently — every line just fell
  back to being stored as an unparsed "continuation," with no signal
  anywhere, not even the container logs. Each fetch now checks what
  fraction of a batch (10+ lines) came back as continuations; past 50%,
  it logs a warning and shows a "Format-Warnung: <source>" in the status
  bar. A one-off traceback or two won't trigger it — only a batch that's
  mostly unparsed will.
- "An Paste senden" button next to "Exportieren" — uploads the current
  filter's export to openWB's own paste instance
  ([lucko/paste](https://github.com/lucko/paste), self-hosted at
  `paste.openwb.de`) and copies the resulting shareable link to the
  clipboard. Same filter/disabled-while-live rules as the file export
  above. New `paste_upload_url`/`paste_view_url` settings (defaulting to
  the verified working endpoints, `bytebin.openwb.de/post` and
  `paste.openwb.de/`) in case that ever changes or you'd rather use your
  own instance.
- Quick Zeitraum buttons (15 Min / 30 Min / 1 Std / 2 Std) that set from/to
  to "now minus N" through "now" and load immediately — no more manually
  picking both datetime fields for the common "just show me recently"
  case. Raised the Zeitraum line cap from 20000 to 100000 to go with it
  (see below) — even a 15-minute window can be tens of thousands of lines
  on a verbose source, so the old cap would have truncated the shortest
  preset almost every time.
- "Zeilen pro Seite" setting in the settings panel (default raised from a
  hardcoded 1000 to 5000, adjustable 100-20000) — controls the page size
  for both "Heute (live)" tail mode and normal day paging.
- "Zeitraum" from/to datetime picker in the header, as an alternative to
  the day dropdown, for viewing an arbitrary time window instead of a
  whole calendar day — backed by new `from`/`to` filters on `/api/logs`
  and `/api/logs/export` (`ts >= ` / `ts < `, independent of the existing
  `day` equality filter). Fetches the whole selected window in one request
  (up to 100000 lines, `/api/logs`'s own cap raised to match) instead of
  paging 1000 at a time — you already bounded it by picking from/to, so
  paging through it in 1000-line chunks defeated the point. Past that cap
  the view shows only the earliest 100000 lines plus a notice to narrow
  the range further.
- Newest-first display toggle (the ⇅ button next to "Exportieren"),
  remembered in `localStorage`. Purely a display-order flip on already-
  fetched lines; doesn't change what's fetched or how paging works.
- Optional in-app self-update: an "Update" button in the settings panel
  runs `git pull --ff-only` against the repo checkout (bind-mounted onto
  the container's `WORKDIR` by `docker-compose.yml`) and restarts the
  process, which `restart: unless-stopped` brings back up with the new
  code — no Docker socket, no image rebuild, no sibling container. Falls
  back to telling you to `docker compose up -d --build` yourself if the
  pull touched `requirements.txt`/`Dockerfile`. A "Prüfen" button checks
  for an update (`git fetch` + compare) without applying it. See
  `DEPLOYMENT.md`.
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
