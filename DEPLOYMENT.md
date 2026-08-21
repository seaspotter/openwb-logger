# Deployment

## Quick start

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
```

This starts two services: `timescaledb` (TimescaleDB on Postgres 16, data
in the `timescale_data` named volume) and `app` (this tool, port 8080).

## Running on Proxmox (Ubuntu Server)

Two options for the container itself; everything after that is identical
to any other Ubuntu host.

**LXC** (lighter, needs one tweak): create an unprivileged Ubuntu Server
22.04/24.04 LXC — 2 vCPU, 2–4 GB RAM, 15–20 GB disk (TimescaleDB is the
heavier of the two services). Docker needs kernel features LXC blocks by
default, so before first boot: **Resources → Options → Features**, enable
**Nesting** and **keyctl**. Without this, `docker compose up` fails or the
containers won't start.

**VM** (simpler, no caveats): a normal Ubuntu Server VM (ISO or
cloud-init), same sizing. Docker just works.

Either way:

```bash
curl -fsSL https://get.docker.com | sh
git clone https://github.com/seaspotter/openwb-logger.git
cd openwb-logger
cp .env.example .env
nano .env   # set a real POSTGRES_PASSWORD
docker compose up -d --build
```

Then open `http://<container-ip>:8080` and set up openWB's address from
the settings panel. One thing worth checking first: the container needs
to be on a network/VLAN that can actually reach the openWB device (the
same bridge as your LAN, not an isolated Proxmox-internal network) — on
the wrong network, every source just shows a `last_error` in the status
bar.

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
| `TZ` | `Europe/Berlin` | Container timezone. Affects only app-generated timestamps (e.g. "Letzter Abruf" in the status bar) — log lines' own `ts` come from openWB's log text and are unaffected. Override in `.env` if you're not in that zone. |
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
`app/db.py`) — no separate migration step. One exception worth expecting:
the first restart after the indexes added for search/filter performance
land (`idx_log_lines_source_ts`, `idx_log_lines_raw_trgm`) will take longer
than usual if `log_lines` is already large, since building an index over
existing data takes a moment (and briefly locks each chunk while it does).
Every restart after that is unaffected — `IF NOT EXISTS` skips rebuilding
them.

### Self-update from the UI

The settings panel has an "Update" button that runs `git pull --ff-only`
against the repo checkout, then restarts the process so it picks up the
new code — no Docker socket, no image rebuild, no separate container
involved. This works because `docker-compose.yml` bind-mounts the whole
repo onto the container's `WORKDIR` (`- .:/app`), so the files the running
process reads *are* the git checkout; `git pull` updates them in place,
and `docker-compose`'s `restart: unless-stopped` brings the process back
up immediately after it exits (see `app/updater.py`). If you commented out
that bind mount for a fully immutable deployment, the Update button and
`/api/update/*` endpoints just report `self_update_available: false` and
the UI hides them, rather than showing a confusing git error.

**This only covers pure code/template changes.** If a pull brings in a
`requirements.txt` or `Dockerfile` change, the endpoint deliberately does
*not* restart — the new dependency isn't installed in the running
container yet — and instead tells you to run:
```bash
docker compose up -d --build
```
Check `CHANGELOG.md` after an update if you're unsure whether that applies.

**Security note**: the web UI has no authentication (see below). Since
self-update no longer needs the Docker socket, the worst a compromised
request can do here is pull whatever's on the configured git remote/branch
and restart the process — not take over the host. Still, if the UI is
reachable beyond your LAN, put it behind an authenticated reverse proxy.

## Running behind a reverse proxy

The web UI has **no authentication**, deliberately — this is designed for
a trusted home network, not built as an in-app feature. If it needs to be
reachable beyond your LAN, put it behind a reverse proxy with auth in
front of it (e.g. [Authelia](https://www.authelia.com/), the same
approach used for `knxpilot`) rather than exposing port 8080 directly.

## Troubleshooting

- **"Nicht erreichbar" in the status bar** (or a source's `last_error` in
  `/api/status` directly): the fetcher couldn't reach that log's URL —
  check the base URL/ramdisk path in the settings panel and that the
  openWB device is reachable from the container. Use the "Jetzt abrufen"
  (fetch now) button in the UI to retry immediately and see the result
  without waiting for the next scheduled poll.
- **Gaps keep appearing** (`total_gaps_detected` growing in `/api/status`):
  the poll interval is too long relative to how fast that log rotates —
  shorten the fetch interval in the settings panel.
- **`create_hypertable` errors on startup**: the `timescaledb` image wasn't
  used for the Postgres service (a plain `postgres` image won't have the
  extension) — check `docker-compose.yml` still points at
  `timescale/timescaledb:latest-pg16`.
- **Update button is missing/disabled**: `docker-compose.yml`'s `- .:/app`
  bind mount is commented out, or `/app/.git` doesn't exist for some other
  reason (e.g. deployed from a tarball rather than `git clone`) — see
  "Self-update from the UI" above.
- **`git pull` fails inside the container with a permission or "dubious
  ownership" error**: the container runs as root (see Dockerfile), so
  ownership mismatches are usually not the issue — more likely the repo
  has local modifications or diverged history. `git -C . status` on the
  host (same directory) will show what's blocking the fast-forward.
