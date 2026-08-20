# Deployment

## Quick start

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
```

This starts two services: `timescaledb` (TimescaleDB on Postgres 16, data
in the `timescale_data` named volume) and `app` (this tool, port 8080).

## Configuration

Everything below is read from environment variables **only as the initial
seed** on first boot, written once into the `app_settings` table. After
that, change it from the settings panel (gear icon) in the web UI — it
takes effect on the next poll, no restart needed.

| Variable | Default | Meaning |
|---|---|---|
| `OPENWB_BASE_URL` | `http://openwb` | Base URL of your openWB web server, no trailing slash |
| `OPENWB_RAMDISK_PATH` | `/openWB/ramdisk` | Ramdisk directory below the base URL |
| `FETCH_INTERVAL_SECONDS` | `600` | Poll interval. Keep this well under how long it takes `main.log` to fill up (roughly an hour by default), so a missed poll can still be recovered from its `.1` backup |
| `RETENTION_DAYS` | `30` | How many days of log lines to keep |

Which logs are collected (`main` only, by default) is set from the UI, not
an env var — see the settings panel.

These are deployment-level, fixed for the life of the container (changing
them means editing `.env` and restarting). Rotation depth (how many
backups a log has) isn't here — it's per-source, defined in
`app/log_catalog.py` to match openWB's own logger config:

| Variable | Default | Meaning |
|---|---|---|
| `HTTP_TIMEOUT_SECONDS` | `15` | Per-request HTTP timeout |
| `TAIL_WINDOW` | `50` | Lines of overlap kept per source to detect duplicates/rotation between polls |
| `DATABASE_URL` | `postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger` | Postgres/TimescaleDB connection string (docker-compose sets this for you from `POSTGRES_PASSWORD`) |
| `POSTGRES_PASSWORD` | — | Set a real password in `.env`; used by both services |
| `PORT` | `8080` | Web UI / API port |

## State and backups

- The `timescale_data` named volume is the *only* state — back it up like
  any Postgres data directory if the history matters to you
  (`pg_dump`/`pg_basebackup`, or snapshot the volume).
- The `app` container is stateless: it can be freely restarted or
  recreated. Poll position (per source) and runtime settings both live in
  the database, not on disk.

## Upgrading

```bash
git pull
docker compose up -d --build
```

Schema changes are additive and applied automatically at startup
(`CREATE ... IF NOT EXISTS` / `ALTER ... ADD COLUMN IF NOT EXISTS` in
`app/db.py`) — no separate migration step.

## Running behind a reverse proxy

The web UI has **no authentication**. This is designed for a trusted home
network; if it needs to be reachable beyond your LAN, put it behind a
reverse proxy (Caddy, Traefik, nginx) with auth in front of it rather than
exposing port 8080 directly.

## Troubleshooting

- **`/api/status` shows a `last_error` for a source**: the fetcher couldn't
  reach that log's URL — check `OPENWB_BASE_URL`/`OPENWB_RAMDISK_PATH` (or
  their settings-panel equivalents) and that the openWB device is
  reachable from the container.
- **Gaps keep appearing** (`total_gaps_detected` growing in `/api/status`):
  the poll interval is too long relative to how fast that log rotates —
  shorten `FETCH_INTERVAL_SECONDS` for that log, or via the settings panel.
- **`create_hypertable` errors on startup**: the `timescaledb` image wasn't
  used for the Postgres service (a plain `postgres` image won't have the
  extension) — check `docker-compose.yml` still points at
  `timescale/timescaledb:latest-pg16`.
