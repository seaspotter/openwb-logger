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

### Self-update from the UI (optional)

The settings panel has an "Update" button (`POST /api/update`) that does
the above from inside the app itself: `git pull`, then rebuild and recreate
the stack. It's **off by default** and needs an explicit opt-in, because it
requires mounting the Docker socket into the app container — root-equivalent
access to the host — which the base `docker-compose.yml` deliberately never
does on its own.

To enable it:

1. In `.env`, set `HOST_REPO_DIR` to this repo's **absolute path on the
   Docker host** (e.g. `/home/pi/openwb-logger`) — not a path inside any
   container. This is needed because the rebuild runs in a short-lived
   sibling container launched over the socket ("Docker-outside-of-Docker");
   volume paths for that sibling are resolved by the host daemon, so only a
   host-absolute path works.
2. Start (or re-up) with the override file:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.selfupdate.yml up -d --build
   ```

**Think about this before enabling it**: the web UI has no authentication
(see below). Combined with docker-socket access, anyone who can reach the
UI can trigger a rebuild, and anything that ever compromises the app
process gets host root through the socket. This is fine on a trusted LAN
where you're the only one who can reach it; if the UI is reachable more
broadly, put it behind an authenticated reverse proxy *before* enabling
self-update, not after.

What actually happens on click: `git pull --ff-only` runs in this
container against the bind-mounted repo; if that succeeds, a detached
`docker:27-cli` sibling container is launched (over the socket) to run
`docker compose up -d --build`, independent of this container's own
lifecycle — necessary because that command's job is to replace the very
container that would otherwise be running it. The HTTP request returns as
soon as the rebuild is *launched*, not when it *finishes*; expect the page
to need a manual reload after ~30–60s once the container comes back with
the new image. The outcome of the git-pull step (or a config error if
`HOST_REPO_DIR` isn't set) is persisted and shown in the settings panel
next time you open it, via `GET /api/update/status`.

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
- **Update button is disabled**: `HOST_REPO_DIR` isn't set, or you're not
  running with `-f docker-compose.selfupdate.yml` — see "Self-update from
  the UI" above.
- **Update button says it started, but nothing changes**: check the
  sibling updater container's own output —
  `docker ps -a --filter ancestor=docker:27-cli` to find it (it's `--rm`,
  so it disappears once done; re-trigger and run that command quickly if
  you need to catch its logs) — and confirm `HOST_REPO_DIR` in `.env`
  really is this repo's path *on the host*, not `/repo` or any other
  in-container path.
