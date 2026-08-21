# openwb-logger

openWB keeps only about an hour of detail in `main.log` on its ramdisk
(5&nbsp;MB, rotated with a handful of backups). This tool polls openWB's
logs over HTTP on a configurable interval, merges them gap-free, and
stores them in TimescaleDB so you get a complete, searchable history
instead of a rolling hour. A small web UI lets you browse, live-tail,
filter, search, and export it — light or dark, your call.

## Features

- **Polls openWB's live logs over plain HTTP** — `main.log` by default,
  optionally any of openWB's other ramdisk logs (chargelog, mqtt, soc,
  internal chargepoint) — on a configurable interval.
- **Gap-free merging**: each poll only stores lines it hasn't seen yet. If
  a rotation happens between two polls, it automatically falls back to
  openWB's own rotated backups (`main.log.1` etc.) to recover the lines
  that would otherwise fall through the gap. On a source's very first
  poll, it backfills from those same backups instead of only capturing
  lines going forward, so pre-existing history isn't lost either.
- **Structured storage in TimescaleDB**: every line is parsed into
  timestamp, logger, level, thread, and message, so you can filter by
  level, source, or date instead of grepping text — backed by a `pg_trgm`
  index for search and cursor-based paging that stays fast regardless of
  how deep into a busy day you page.
- **Retention** is enforced by a native TimescaleDB retention policy — old
  chunks are dropped automatically, no cron job.
- **All setup lives in the app itself, not environment variables**: where
  openWB is, which logs to collect, retention, poll interval, and page
  size are all configured from a settings panel in the UI (in German) and
  take effect immediately — no redeploy needed. The only things left in
  `.env` are pure infra wiring (DB password, port, timezone).
- **Web UI** (German): browse any day or an arbitrary time range (with
  15&nbsp;Min/30&nbsp;Min/1&nbsp;Std/2&nbsp;Std quick buttons), live-tail
  today with auto-refresh, trigger an immediate fetch on demand, filter by
  source/level, search, export the current filter as a plain-text file or
  send it straight to a paste service for a shareable link, and toggle
  light/dark theme.
- **Optional in-app self-update**: an "Update" button that pulls the
  latest code and restarts, no Docker socket or image rebuild required for
  pure code changes — see [DEPLOYMENT.md](DEPLOYMENT.md).
- **MCP server** at `/mcp`, alongside the web UI on the same port —
  search/tail/export the collected logs from an AI assistant (Claude
  Desktop, Claude Code, ...) directly, no browser needed. See
  [DEPLOYMENT.md](DEPLOYMENT.md).

## How it works

```
openWB device                openwb-logger                 you
┌─────────────┐   HTTP GET   ┌──────────────────┐   HTTP   ┌────────┐
│ ramdisk/     │─────────────▶│ fetcher (poll)   │          │ browser│
│ main.log,    │  every N min │        │         │          │        │
│ chargelog... │◀─ (on gap) ──│        ▼         │          │        │
└─────────────┘              │  parse + insert  │          │        │
                              │        ▼         │          │        │
                              │  TimescaleDB      │◀── SQL ──│ web UI │
                              │  (log_lines,       │          └────────┘
                              │   app_settings,     │
                              │   retention policy)│
                              └──────────────────┘
```

Full breakdown of each module in [CLAUDE.md](CLAUDE.md).

## Quick start

```bash
git clone https://github.com/seaspotter/openwb-logger.git
cd openwb-logger
cp .env.example .env
# edit .env: set a real POSTGRES_PASSWORD

docker compose up -d --build
```

Open http://localhost:8080, click the gear icon (⚙), and enter your
openWB's address, the logs to collect, retention, and poll interval. That's
the only setup step — everything else is configured through the app.

## Docs

- [MANUAL.md](MANUAL.md) — using the web UI: browsing, live-tail, search,
  Zeitraum, export, settings, self-update
- [DEVELOPMENT.md](DEVELOPMENT.md) — local dev setup, running tests, adding
  a new log source
- [DEPLOYMENT.md](DEPLOYMENT.md) — full configuration reference, backups,
  upgrades, running behind a reverse proxy
- [ROADMAP.md](ROADMAP.md) — what's built, what's next
- [CHANGELOG.md](CHANGELOG.md) — notable changes by version
- [CLAUDE.md](CLAUDE.md) — architecture notes for whoever (human or Claude)
  touches this code next

## Known limitations

- Timestamps stored from log lines are exactly as openWB writes them
  (naive, no timezone conversion) — that's the device's own wall-clock
  time. App-generated timestamps (e.g. the status bar's last-fetch time)
  use the container's own clock instead, so they need `TZ` set correctly
  (see [DEPLOYMENT.md](DEPLOYMENT.md)) to show your local time rather than
  UTC.
- No authentication on the web UI — see [DEPLOYMENT.md](DEPLOYMENT.md).
