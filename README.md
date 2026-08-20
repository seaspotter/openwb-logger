# openwb-logger

openWB keeps only about an hour of detail in `main.log` on its ramdisk
(5&nbsp;MB, rotated with a handful of backups). This tool polls that log over
HTTP every few minutes, parses each line, and stores it in TimescaleDB so you
get a complete, searchable history instead of a rolling hour. A small web UI
lets you browse, live-tail, filter, and export it.

## Features

- **Polls openWB's live log over plain HTTP** (`/openWB/ramdisk/main.log`) on
  a configurable interval.
- **Gap-free merging**: each poll only stores lines it hasn't seen yet. If a
  rotation happens between two polls, it automatically falls back to
  openWB's own rotated backups (`main.log.1` etc.) to recover the lines that
  would otherwise fall through the gap.
- **Structured storage in TimescaleDB**: every line is parsed into
  timestamp, logger, level, thread, and message, so you can filter by level
  or date instead of grepping text.
- **Retention** is enforced by a native TimescaleDB retention policy
  (`RETENTION_DAYS`) — old chunks are dropped automatically, no cron job.
- **Web UI**: browse any day, live-tail today with auto-refresh, filter by
  level, search, and export the current view (or a specific line range) as
  a plain-text snippet.

## How it works

```
openWB device                openwb-logger                 you
┌─────────────┐   HTTP GET   ┌──────────────────┐   HTTP   ┌────────┐
│ ramdisk/     │─────────────▶│ fetcher (poll)   │          │ browser│
│ main.log     │  every N min │        │         │          │        │
│ main.log.1-4 │◀─ (on gap) ──│        ▼         │          │        │
└─────────────┘              │  parse + insert  │          │        │
                              │        ▼         │          │        │
                              │  TimescaleDB      │◀── SQL ──│ web UI │
                              │  (log_lines,       │          └────────┘
                              │   retention policy)│
                              └──────────────────┘
```

1. `app/fetcher.py` fetches `main.log`, compares it against the last known
   tail of lines (kept in a small `fetcher_state` table), and extracts only
   the genuinely new lines. See `app/log_merge.py` for the overlap/gap
   detection, which is pure logic and unit tested.
2. `app/log_parse.py` parses openWB's `DETAILED` log format
   (`timestamp - {logger:line} - {LEVEL:thread} - message`) into structured
   fields. Lines that don't match (traceback continuations) inherit context
   from the previous line and are stored verbatim.
3. Rows land in a single hypertable, `log_lines`, partitioned by time.
4. A TimescaleDB retention policy drops chunks older than `RETENTION_DAYS`.
5. `app/web.py` exposes a small JSON API the single-page UI in
   `app/templates/index.html` polls (no build step, plain JS).

## Quick start

```bash
git clone https://github.com/seaspotter/openwb-logger.git
cd openwb-logger
cp .env.example .env
# edit .env: set OPENWB_BASE_URL to your openWB's address, and a real
# POSTGRES_PASSWORD

docker compose up -d --build
```

Open http://localhost:8080.

## Configuration

All via environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `OPENWB_BASE_URL` | `http://openwb` | Base URL of your openWB web server, no trailing slash |
| `OPENWB_LOG_PATH` | `/openWB/ramdisk/main.log` | Path to the live log |
| `OPENWB_BACKUP_COUNT` | `4` | How many rotated backups (`.1`..`.N`) openWB keeps, used for gap recovery |
| `FETCH_INTERVAL_SECONDS` | `600` | Poll interval. Keep this well under how long it takes `main.log` to fill up (roughly an hour by default), so a missed poll can still be recovered from `.1` |
| `RETENTION_DAYS` | `30` | How many days of log lines to keep |
| `TAIL_WINDOW` | `50` | Lines of overlap kept to detect duplicates/rotation between polls; the default is generous for typical openWB traffic |
| `DATABASE_URL` | `postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger` | Postgres/TimescaleDB connection string (docker-compose sets this for you) |
| `PORT` | `8080` | Web UI / API port |

## Development

Requires Python 3.12+ and a local TimescaleDB (easiest via Docker):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# start just the database
docker compose up -d timescaledb

export DATABASE_URL=postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger
export OPENWB_BASE_URL=http://10.1.5.32   # or wherever your openWB is

uvicorn app.main:app --reload --port 8080
```

Run the unit tests (pure logic only — `log_merge` and `log_parse` — no
database or network needed):

```bash
pytest
```

## Deployment notes

- The `timescale_data` named volume is the only state; back it up like any
  Postgres data directory if the history matters to you.
- The app container itself is stateless — it can be freely restarted;
  polling position is tracked in the `fetcher_state` table, not on disk.
- This is designed for a trusted home network. The web UI has no
  authentication — put it behind a reverse proxy with auth, or restrict
  access at the network level, if it's reachable beyond your LAN.

## API

- `GET /api/dates` — days with any data
- `GET /api/levels` — distinct log levels seen
- `GET /api/logs?day=&search=&level=&offset=&limit=&tail=` — paginated (or
  tail-mode) lines
- `GET /api/logs/export?day=&search=&level=&start=&end=` — plain-text
  download of the matching range
- `GET /api/status` — fetcher health, row counts, last error

## Known limitations

- Timestamps are stored exactly as openWB writes them (naive, no timezone
  conversion) — that's the device's own wall-clock time.
- Only `main.log` is fetched; openWB's other logs (`chargelog`, `mqtt`,
  etc.) aren't in scope.
- Search is a plain `ILIKE` scan, fine at the volume a single openWB
  produces; if that ever becomes a bottleneck, a `pg_trgm` index on `raw`
  would be the next step.
