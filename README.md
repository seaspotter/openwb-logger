# openwb-logger

openWB keeps only about an hour of detail in `main.log` on its ramdisk
(5&nbsp;MB, rotated with a handful of backups). This tool polls openWB's
logs over HTTP on a configurable interval, merges them gap-free, and
stores them in TimescaleDB so you get a complete, searchable history
instead of a rolling hour. A small web UI lets you browse, live-tail,
filter, and export it — light or dark, your call.

## Features

- **Polls openWB's live logs over plain HTTP** — `main.log` by default,
  optionally any of openWB's other ramdisk logs (chargelog, mqtt,
  smarthome, soc, ...) — on a configurable interval.
- **Gap-free merging**: each poll only stores lines it hasn't seen yet. If
  a rotation happens between two polls, it automatically falls back to
  openWB's own rotated backups (`main.log.1` etc.) to recover the lines
  that would otherwise fall through the gap.
- **Structured storage in TimescaleDB**: every line is parsed into
  timestamp, logger, level, thread, and message, so you can filter by
  level, source, or date instead of grepping text.
- **Retention** is enforced by a native TimescaleDB retention policy — old
  chunks are dropped automatically, no cron job.
- **Runtime settings, no restart needed**: where openWB is, which logs to
  collect, retention, and poll interval are all editable from a settings
  panel in the UI and take effect on the next poll.
- **Web UI**: browse any day, live-tail today with auto-refresh, filter by
  source/level, search, export the current view (or a specific line range)
  as a plain-text snippet, and switch between light, dark, or
  system-matched theme.

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
# edit .env: set OPENWB_BASE_URL to your openWB's address, and a real
# POSTGRES_PASSWORD (these are just initial defaults — everything is
# editable later from the settings panel in the UI)

docker compose up -d --build
```

Open http://localhost:8080 and click the gear icon to fine-tune source,
retention, and poll interval.

## Docs

- [DEVELOPMENT.md](DEVELOPMENT.md) — local dev setup, running tests, adding
  a new log source
- [DEPLOYMENT.md](DEPLOYMENT.md) — full configuration reference, backups,
  upgrades, running behind a reverse proxy
- [ROADMAP.md](ROADMAP.md) — what's built, what's next
- [CHANGELOG.md](CHANGELOG.md) — notable changes by version
- [CLAUDE.md](CLAUDE.md) — architecture notes for whoever (human or Claude)
  touches this code next

## Known limitations

- Timestamps are stored exactly as openWB writes them (naive, no timezone
  conversion) — that's the device's own wall-clock time.
- Search is a plain `ILIKE` scan, fine at the volume a single openWB
  produces; if that ever becomes a bottleneck, a `pg_trgm` index on `raw`
  would be the next step.
- No authentication on the web UI — see [DEPLOYMENT.md](DEPLOYMENT.md).
