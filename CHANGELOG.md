# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Versions follow [semver](https://semver.org/); see `DEVELOPMENT.md` for
what that means in practice for this project.

## [Unreleased]

## [0.3.0] - 2026-08-27

### Added
- Compression-job health check, alongside the existing retention-job one:
  compression runs via the same kind of TimescaleDB background job
  (`policy_compression`) and carries the same blind-spot risk -- checked
  identically (a warning-level alert, since a stuck compression job means
  chunks stay larger than they could be, not that data is never deleted
  the way a stuck retention job means). No matching one-click repair
  yet, unlike retention's -- that fix targeted a specific, diagnosed bug;
  nothing's been diagnosed for compression-job failures yet, so building
  a "fix" now would just be guessing.
- Retention-job health check + one-click repair. TimescaleDB's own
  retention job can get permanently stuck failing every run with
  `ERROR: no chunk found with ID N` -- a real upstream TimescaleDB bug
  (a dangling internal catalog reference to an already-dropped chunk
  that never gets cleaned up), not anything in this project's own
  retention logic, which just calls TimescaleDB's built-in
  `add_retention_policy` and lets it manage everything. Confirmed live
  on a real installation: silently never dropped a single chunk despite
  a 7-day retention setting, growing disk usage unbounded until it
  neared full. `/api/status` now surfaces the job's health (new
  "!" alert when it's stuck), and the settings panel shows a
  Retention-Job status line with a **Reparieren** button (confirmation
  dialog first) that finds and removes any orphaned
  `chunk_constraint`/`dimension_slice` catalog rows -- deliberately a
  human-triggered action, not automatic, since it pokes at
  TimescaleDB's own undocumented internal tables; touches no actual log
  data. Full diagnosis/manual-fix steps also documented in
  `DEPLOYMENT.md`'s troubleshooting section for anyone who hits this
  before self-update brings in the button.

### Changed
- Three disk-usage optimizations, all driven by real measurements on a
  live 15M-row instance:
  - Chunk interval dropped from TimescaleDB's 7-day default to 1 day.
    With 7-day chunks and 7-day retention, a chunk can only be dropped
    once it's *entirely* past the cutoff, so steady-state usage sawtoothed
    between roughly 7 and 14 days of data rather than holding near the
    configured 7 -- 1-day chunks let retention track the setting far more
    closely. Only affects chunks created from here on.
  - Dropped a genuinely redundant single-column index on `source`: the
    existing `(source, ts DESC)` index already serves a plain
    `WHERE source = X` via its leading column just as well. Measured at
    ~104 MB for zero functional benefit.
  - Enabled TimescaleDB native compression on chunks older than 1 day.
    The GIN trigram search index alone measured 3.65 GB on a real
    instance -- bigger than the actual log data (4.24 GB) -- and
    compression typically shrinks repetitive text like this 10-20x. Real
    trade-off, taken deliberately: compressed chunks don't maintain
    btree/GIN indexes the normal way, so free-text search reaching into
    data older than 1 day falls back to a slower decompress-and-scan
    instead of an index scan. Browsing/filtering by day/level/source
    stays fast either way (TimescaleDB's compression is specifically
    optimized for that access pattern), and the actively-written chunk
    stays uncompressed, so live-tail and recent search are unaffected.
    Compression itself happens gradually via TimescaleDB's own background
    job, not instantly on upgrade.

### Fixed
- `/api/dates` (the "Tag" dropdown) took 22+ seconds to load on a real
  15M-row instance: `SELECT DISTINCT ts::date FROM log_lines` scans
  close to the entire table to find a handful of distinct days, since
  `ts::date` is a computed expression that TimescaleDB's SkipScan
  optimization (which already makes `/api/levels`'s similar DISTINCT
  query fast, confirmed via EXPLAIN ANALYZE) can't apply to. Replaced
  with a day range generated from `min(ts)`/`max(ts)` instead (already
  cheap, index-optimized -- confirmed 22s → 3.9ms on the same real
  instance) -- assumes continuous day-to-day coverage, true for an
  always-on poller; a day with genuinely zero rows just shows "keine
  Zeilen" if picked.

## [0.2.1] - 2026-08-23

### Changed
- Bumped `jinja2` 3.1.4 → 3.1.6 (fixes two GHSA sandbox-breakout
  advisories flagged by newly-enabled Dependabot alerts -- not actually
  exploitable here, since this app only ever renders one fixed,
  developer-authored template via a plain, non-sandboxed environment, no
  untrusted template content) and dev-only `pytest` 8.3.3 → 9.1.1 (fixes
  a tmpdir-handling advisory affecting test runs, never the running
  container). Needed bumping the previously-unpinned `pytest-asyncio` to
  1.4.0 alongside it (0.24.0 hard-requires `pytest<9`) -- now pinned
  explicitly in `requirements-dev.txt` for the first time. Verified the
  full combination resolves cleanly (`pip check`) and the test suite
  passes before landing this.

## [0.2.0] - 2026-08-21

### Added
- MCP `get_storage_info` tool: total row count, oldest/newest timestamp,
  a table/index/toast/total byte breakdown of the whole `log_lines`
  hypertable, per-source row counts, and the current retention setting --
  answers "how much disk is my log data using" without hand-writing SQL,
  reusing the exact queries used to actually diagnose that live tonight.
- "Exportierte Datei komprimieren (.gz)" checkbox in the settings panel —
  a browser-local preference (like theme/sort order, not a server-side
  setting), so "Exportieren" downloads a real `.gz` file instead of plain
  text. Sends `Content-Type: application/gzip` rather than
  `Content-Encoding: gzip`, since the latter is transparently decompressed
  by the browser before saving, defeating the point of a smaller
  download. Unrelated to "An Paste senden", which already always gzips
  its upload regardless of this setting.
- Alerts button now supports acknowledging: opening the modal remembers
  exactly which alert texts you've seen (persisted in `localStorage`), so
  the badge goes quiet again afterward instead of staying lit for a
  rolling condition (e.g. "X ERROR-Zeile(n) in der letzten Stunde") that
  never fully clears on its own. Lights back up on its own if anything
  actually changes -- a new alert appears, or an existing one's count
  changes (a different string than what was acknowledged) -- no
  time-based re-alarm needed.

### Changed
- `docker-compose.yml`'s `app` service no longer needs a hand-assembled
  `DATABASE_URL` -- it now gets the same `POSTGRES_PASSWORD` variable the
  `timescaledb` service already uses, and `app/config.py` builds the
  connection string itself (user/db/host/port are fixed values matching
  that service, not something a standard deployment needs to vary). Only
  one place to set the password now instead of two copies of the same
  secret to keep in sync -- a real mismatch between them (rather than a
  bad password outright) is exactly what caused an authentication failure
  while setting up a NAS/Portainer deployment. `DATABASE_URL` still works
  and still wins outright if set, as an escape hatch for anything that
  deviates from the standard setup (local dev, a differently-named host).
- Dropped "all-in-one image" from `ROADMAP.md` -- considered and decided
  against. The current two-service `docker-compose.yml` already covers
  what a bundled image would have, without giving up independent
  `docker compose pull` upgrades of the database image. Documented as a
  deliberate choice in `DEPLOYMENT.md` rather than an unstarted item.
- `DEPLOYMENT.md` gained a generic "Running via Portainer (NAS, etc.)"
  section (prebuilt image, bind-mount the database data wherever you
  want, no self-update since there's no git checkout to pull) -- written
  up generically after actually working through a real NAS/Portainer
  deployment.
- Dropped the `raw` column from `log_lines`. For a DETAILED-format line, it
  stored the entire original text -- timestamp, logger, line number,
  level, thread, *and* message -- even though all but the message are
  already stored as their own columns (measured ~40% of that column's
  bytes as pure duplication on a real 1M+ row instance). The exact
  original line is now reconstructed on read from the structured columns
  instead (`RAW_EXPR` in `app/db.py`), so display, export, and search
  ("Suchen") are all byte-for-byte unchanged -- verified against a real
  Postgres instance (DETAILED/SHORT/continuation lines, and a simulated
  upgrade from the old schema) before landing this, including one real
  bug caught that way: plain `to_char()` isn't IMMUTABLE, so it can't be
  used directly in the expression index backing search -- fixed with a
  small IMMUTABLE wrapper function instead.

### Fixed
- Changing the level/source/search filter while live-tailing "Heute
  (live)" silently jumped to the start of the day (ascending order from
  midnight) instead of staying near "now": turning off Live resets the
  paging cursor to null, but the view then fell through to the plain
  day-paging branch with no cursor, which defaults to the first page.
  Pre-existing since the original keyset-pagination rewrite, not a
  regression from anything recent -- confirmed via `git log -S` before
  fixing. Now shows the most recent matching lines instead (the same
  "tail" query live-follow itself uses) whenever there's no explicit
  paging cursor and you're on "today", independent of whether Live is
  still checked -- only the *continuous* 5s auto-refresh, and disabling
  export while it's active, still depend on the Live checkbox itself.
- Settings panel's "Prüfen"/"Update" buttons were only greyed out, not
  hidden, on a deployment with no bind-mounted git checkout to update in
  place (e.g. a plain `image:` deployment, as opposed to `build: .`) --
  permanently dead buttons sitting there regardless of deployment type.
  Now hidden entirely in that case (`DEPLOYMENT.md` already documented
  this as the intended behavior; the frontend just didn't match it).

## [0.1.0] - 2026-08-21

### Added
- `LICENSE`: GNU Affero General Public License v3.0 or later — same
  license as the sibling project `knxpilot`, copied verbatim. Chosen
  because this is a network service; AGPL closes the "SaaS loophole"
  plain GPL has. `app/main.py` now carries the matching copyright/license
  header, and `README.md` gets a short "License" section explaining why.
- Project logo (`docs/logo.svg`, the same green "log lines" glyph used as
  the in-app favicon/header mark) and a real screenshot in `README.md`.
- Alerts indicator: a quiet "!" button in the header (next to "Jetzt
  abrufen") replaces the scattered inline status-bar warnings
  ("Fehler:"/"Nicht erreichbar:"/"Format-Warnung:") with one place to
  check — badge only lights up when there's something to see, no popups,
  no external notifications. Aggregates whole-cycle fetch failures,
  per-source unreachability, format-mismatch warnings, unrecovered gaps,
  and (new) a per-source count of actual ERROR-level log lines in the
  last hour, which nothing previously surfaced at all — clicking shows
  the full list in a modal.
- MCP server at `/mcp`, mounted on the same FastAPI app as the web UI
  (same port, same DB pool, same no-auth trust model) via the Streamable
  HTTP transport — `search_logs` (day/range/level/source/text filters),
  `tail_logs` (latest N lines), `export_logs` (everything matching a
  filter, as plain text), and an `openwb://sources` resource listing
  valid source names. Response sizes are capped much lower than the web
  UI's own limits (e.g. search defaults to 200 lines, max 2000) since
  these flow into an LLM's context window, not a browser's DOM. `mcp` is
  pinned to its 1.x line in `requirements.txt`, not the newer 2.x:
  2.x forces a `starlette` major-version bump that conflicts with
  `fastapi==0.115.0`'s own pin — verified by actually resolving both
  together, not just reading changelogs. Verified end-to-end with the real
  MCP client library (session handshake, `list_tools`, `call_tool`)
  against a locally running instance, not just that it constructs without
  error.
- Multi-arch image publishing: `.github/workflows/docker-publish.yml`
  builds and pushes `ghcr.io/seaspotter/openwb-logger` for amd64 and
  arm64 on every push to `main` and on version tags. `build: .` stays the
  documented, primary deployment path (self-update assumes it); the
  published image is a convenience alternative — see DEPLOYMENT.md. (No
  arm/v7 — see "Changed" below.)
- [MANUAL.md](MANUAL.md): a short reference for the web UI itself
  (toolbar controls, status bar, settings panel), linked from
  `README.md`. `README.md` itself also refreshed — it had drifted behind
  several changes this session (line-range export no longer exists, the
  theme toggle isn't a 3-way system/light/dark cycle, search no longer
  needs a `pg_trgm` caveat since that index now exists).
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
- Initial version: poll openWB's `main.log` over HTTP on an interval.
- Gap-free merge between polls, with automatic recovery from openWB's own
  rotated backups (`main.log.1`-`.4`) when a rotation happens mid-interval.
- Parse each line into structured fields (timestamp, logger, level,
  thread, message) and store in a TimescaleDB hypertable.
- Retention enforced via a native TimescaleDB retention policy.
- Server-rendered web UI: browse by day, live-tail today, filter by level,
  search, export a line range as a plain-text snippet.
- Docker Compose deployment (app + TimescaleDB), `README.md`, `CLAUDE.md`.

### Changed
- Dropped `arm/v7` from the published multi-arch image (now just amd64 and
  arm64) -- the first build attempt for it failed outright in CI (`cffi`,
  pulled in transitively via `cryptography`, needs `libffi-dev` headers to
  compile from source there; `asyncpg` has the same no-prebuilt-wheel
  problem). Every current-gen board (Pi 3/4/5) defaults to a 64-bit OS
  now, so arm/v7 only helps old 32-bit-only installs, a shrinking
  population not worth chasing native-header issues for one at a time.
  The Dockerfile drops back to a single stage as a result -- amd64/arm64
  both have prebuilt wheels for everything in `requirements.txt`, so the
  build stage that existed solely to compile for arm/v7 is gone too.
- Log catalog trimmed to what's actually wanted: `main`, `chargelog`,
  `mqtt`, `soc`, `internal_chargepoint`. Dropped `smarthome`,
  `garbage_collector`, `tracemalloc` entirely (not just default-disabled)
  — anyone who had one of those enabled just has it silently stop being
  polled, their existing rows are untouched. Added `forecast` ahead of
  time (default disabled) for an openWB log that doesn't exist in any
  released version yet — taken from the real, currently-open
  `openWB/core` PR #3782, not guessed.
- Source selection is always exactly one source now, never "all combined"
  — the "Alle Quellen" option is gone, and the dropdown defaults to
  `main` (falling back to whatever's enabled if `main` isn't). Blending
  multiple sources' lines together in one interleaved view was more
  confusing than useful.
- Paste settings simplified: the upload/view URL fields are hidden by
  default behind a new "Eigene Paste-Instanz verwenden" checkbox, so the
  common case (using openWB's own instance) shows nothing to configure at
  all. Checking it reveals the same two fields as before for pointing at
  a different instance.
- New logo: green "log lines" glyph (three bars) instead of the previous
  blue ">_" terminal-prompt mark — more literally about what this tool
  actually does (log viewing), per feedback that the old one "wasn't
  perfect."
- TimescaleDB moved from Postgres 16 to 18 (newest major version it
  currently ships images for; Postgres has no LTS concept, every major
  gets an equal 5-year support window — pg18's runs to Nov 2030 vs.
  pg16's Nov 2028) before this project's first release, so there's no
  public pg16 install base anyone needs to migrate from — every install
  from here on just gets pg18 directly. The data volume is named
  `timescale_data_pg18` rather than `timescale_data` regardless, on the
  general principle that a Postgres major-version bump should always get
  a fresh volume name (mounting a newer major version's image against an
  older one's data directory fails outright), not because of anything
  specific to this move.
- Default fetch interval 600s → 120s and default retention 30d → 7d for
  *new* installs (`DEFAULT_*` in `app/runtime_settings.py`; only seeded
  once, on first boot when no settings row exists yet, so this doesn't
  touch already-configured deployments). Most sources rotate faster than
  the old 10-minute default.
- Branding pass: a small inline-SVG logo (used as both the favicon and a
  header mark), the header title now reads "openWB Logger" with "openWB"
  in accent color, and the light/dark toggle is a proper sun/moon icon
  instead of a single "◐" character (showing the theme currently active,
  not the one a click switches to).
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
- "How it works" diagram in `README.md` was hand-drawn ASCII box art that
  didn't actually line up (box borders and arrows drifted row to row).
  Replaced with a Mermaid flowchart, which GitHub renders natively in
  Markdown -- no more manually counting characters to keep boxes aligned.
- Settings panel's version display showed "unknown" instead of a real
  `git describe` version, still, even after the `safe.directory` fix
  below: `_describe()` unconditionally passed both `--dirty` and an
  explicit commit-ish (`HEAD`, or `@{u}` for the upstream check), which
  git flatly rejects ("Option '--dirty' and commit-ishes cannot be used
  together") -- so every single call failed and silently fell through to
  the "unknown" build-arg default, on every deployment, tags or no tags.
  `--dirty` only makes sense against the working tree, so it's now only
  passed when describing that (no explicit ref); the upstream-ref lookup
  passes `@{u}` with no `--dirty` instead. Reproduced the exact failure
  and confirmed the fix locally before landing it.
- Settings panel's version display showed "unknown" instead of a real
  `git describe` version: the Dockerfile's multi-stage rewrite (for the
  arm/v7 build) dropped the `git config --system --add safe.directory
  /app` line a previous version had. Without it, git refuses every
  command against the bind-mounted repo checkout ("detected dubious
  ownership") since it's owned by the host user, not root (which the
  container runs as) -- silently falling through to the Docker build-arg
  fallback meant for when there's no git checkout at all. Re-added.
- `docker-compose.yml`'s pg18 upgrade shipped with the wrong volume mount
  point and failed to start outright — caught while actually walking
  through the migration. The official Postgres images changed their
  expected mount target starting with major version 18, from
  `/var/lib/postgresql/data` to `/var/lib/postgresql` (letting the image
  manage its own version-specific subdirectory underneath, e.g.
  `18/docker`); mounting at the old path makes the 18+ entrypoint refuse
  to start, treating anything it finds there as leftover data from an
  in-place image upgrade it won't perform automatically. Fixed to mount
  at `/var/lib/postgresql`.
- Per-source fetch errors (e.g. "could not reach ...") were computed by
  the backend and included in `/api/status`, but the status bar never
  actually displayed them — only a whole-cycle failure (a DB problem,
  say) would show anything, so a single unreachable source failed
  silently in the UI. Now shown as "Nicht erreichbar: <source>" (hover for
  the full error), separate from the existing "Fehler:" for whole-cycle
  failures.
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
- `PORT` was read into `Settings.port` but never actually passed to
  uvicorn (the Dockerfile hardcoded `--port 8080`) -- setting a custom
  `PORT` silently did nothing. The Dockerfile's `CMD` now reads `$PORT` at
  container start, and the unused `Settings.port` field was removed.
