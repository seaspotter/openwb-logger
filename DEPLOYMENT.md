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

There is deliberately almost nothing to configure in `.env` — where openWB
is, which logs to collect, retention, and poll interval are all set up
*inside the app* (settings panel, gear icon) after first start, stored in
the database, and take effect on the next poll with no restart. That keeps
`.env` down to pure infra wiring, which matters once this app and its
database are bundled into a single image (see ROADMAP.md) — at that point
there's nothing left here to set before first start at all.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | — | Set a real password in `.env`; used by both services |
| `PORT` | `8080` | Web UI / API port |
| `DATABASE_URL` | `postgresql://openwb_logger:openwb_logger@localhost:5432/openwb_logger` | Postgres/TimescaleDB connection string (docker-compose sets this for you from `POSTGRES_PASSWORD`; only relevant if you're not using docker-compose) |

On first start, the app seeds its settings with hardcoded fallback
defaults (`http://openwb`, `/openWB/ramdisk`, 600s, 30 days — see
`DEFAULT_*` in `app/runtime_settings.py`) and only `main.log` enabled.
Open the settings panel and correct them for your setup.

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
  reach that log's URL — check the base URL/ramdisk path in the settings
  panel and that the openWB device is reachable from the container. Use
  the "Jetzt abrufen" (fetch now) button in the UI to retry immediately
  and see the result without waiting for the next scheduled poll.
- **Gaps keep appearing** (`total_gaps_detected` growing in `/api/status`):
  the poll interval is too long relative to how fast that log rotates —
  shorten the fetch interval in the settings panel.
- **`create_hypertable` errors on startup**: the `timescaledb` image wasn't
  used for the Postgres service (a plain `postgres` image won't have the
  extension) — check `docker-compose.yml` still points at
  `timescale/timescaledb:latest-pg16`.
