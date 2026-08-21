# Deployment

## Quick start

```bash
cp .env.example .env
# edit .env
docker compose up -d --build
```

This starts two services: `timescaledb` (TimescaleDB on Postgres 18, data
in the `timescale_data_pg18` named volume) and `app` (this tool, port
8080).

`build: .` (building locally) is the documented, primary path — it's what
the in-app self-update button assumes (see below). A prebuilt multi-arch
image (amd64/arm64) is also published to
`ghcr.io/seaspotter/openwb-logger` on every release, mainly useful for a
quick `docker run` test or a board where building locally is slow; if you
use it instead of `build: .`, self-update won't have anything to update
in place (no bind-mounted git checkout) and you'd `docker compose pull`
for new versions instead.

Two services (the app and its own TimescaleDB) is the deliberate, final
architecture here, not an interim step toward a bundled single image —
considered and decided against; the current setup already covers what a
single image would have, without giving up the ability to run `docker
compose pull`/upgrade the database image independently of the app.

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

## Running via Portainer (NAS, etc.)

Use the prebuilt image rather than `build: .` here — a Portainer stack
doesn't have (and doesn't need) a git checkout of this repo on the host,
just the compose file itself:

```yaml
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg18
    restart: unless-stopped
    environment:
      POSTGRES_USER: openwb_logger
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: openwb_logger
    volumes:
      - /path/to/your/data/timescaledb:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U openwb_logger"]
      interval: 5s
      timeout: 5s
      retries: 10

  app:
    image: ghcr.io/seaspotter/openwb-logger:latest
    restart: unless-stopped
    depends_on:
      timescaledb:
        condition: service_healthy
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PORT: 8080
      TZ: Europe/Berlin
    ports:
      - "8080:8080"
```

Replace `/path/to/your/data/timescaledb` with wherever you want the
database files to actually live — a bind mount to a real path (rather
than a Docker-managed named volume) is usually the more convenient choice
on a NAS, since it's then visible/backupable through the NAS's own file
manager. Set `POSTGRES_PASSWORD` once, either via Portainer's own
"Environment variables" field on the stack (not the YAML text — this
avoids ever needing to type the same secret twice) or, if you'd rather
keep everything in the compose text itself, replace both
`${POSTGRES_PASSWORD}` occurrences with the same literal value — but
exactly the same value in both places, since a mismatch fails Postgres
authentication outright rather than falling back to anything.

No self-update here (see below) — no bind-mounted git checkout to `git
pull` against, since you're running the published image. Update by
re-pulling the image and redeploying the stack from Portainer instead;
the settings panel's "Prüfen"/"Update" buttons correctly hide themselves
in this case rather than sitting there as dead UI.

## Configuration

There is deliberately almost nothing to configure in `.env` — where openWB
is, which logs to collect, retention, and poll interval are all set up
*inside the app* (settings panel, gear icon) after first start, stored in
the database, and take effect on the next poll with no restart. That keeps
`.env` down to pure infra wiring: the database password, the web port, and
the container's clock.

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | — | Set a real password in `.env`. The **same variable** is passed to both services — `timescaledb` reads it directly, and `app` builds its own connection string from it (`app/config.py`), so there's only ever one place to set it, not two copies of the same secret to keep in sync. |
| `PORT` | `8080` | Web UI / API port |
| `TZ` | `Europe/Berlin` | Container timezone. Affects only app-generated timestamps (e.g. "Letzter Abruf" in the status bar) — log lines' own `ts` come from openWB's log text and are unaffected. Override in `.env` if you're not in that zone. |
| `DATABASE_URL` | — | Full Postgres/TimescaleDB connection string; wins outright over `POSTGRES_PASSWORD` if set. An escape hatch for anything that deviates from this project's own `docker-compose.yml` (local dev against `localhost`, a differently-named Postgres host, a non-standard user/db name) — not needed for the standard two-service setup above. |

On first start, the app seeds its settings with hardcoded fallback
defaults (`http://openwb`, `/openWB/ramdisk`, 120s poll interval, 7 days
retention — see `DEFAULT_*` in `app/runtime_settings.py`) and only
`main.log` enabled. Open the settings panel and correct them for your
setup.

## State and backups

- The `timescale_data_pg18` named volume is the *only* state — back it up
  like any Postgres data directory if the history matters to you
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

## MCP server (for AI assistants)

The app also serves an [MCP](https://modelcontextprotocol.io) server at
`/mcp` (Streamable HTTP transport), alongside the web UI, on the same
port. It exposes four tools — `search_logs` (day/range/level/source/text
filters), `tail_logs` (latest N lines), `export_logs` (everything
matching a filter, as plain text), `get_storage_info` (row count, byte
breakdown, per-source counts, retention setting — the disk-usage picture
without hand-writing SQL) — and an `openwb://sources` resource listing
valid source names. Point any MCP client (Claude Desktop, Claude Code,
etc.) at `http://<host>:8080/mcp` — consult that client's own docs for
how it wants an HTTP-transport server configured, since that varies by
client.

**No separate authentication** — same no-auth, LAN-trust model as the
rest of the app (see below). This doesn't expose anything the web
UI/API didn't already; an MCP client on the same network can read
exactly what a browser already could.

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
  `timescale/timescaledb:latest-pg18`.
- **Update button is missing/disabled**: `docker-compose.yml`'s `- .:/app`
  bind mount is commented out, or `/app/.git` doesn't exist for some other
  reason (e.g. deployed from a tarball rather than `git clone`) — see
  "Self-update from the UI" above.
- **`git pull` fails inside the container with a permission or "dubious
  ownership" error**: the container runs as root (see Dockerfile), so
  ownership mismatches are usually not the issue — more likely the repo
  has local modifications or diverged history. `git -C . status` on the
  host (same directory) will show what's blocking the fast-forward.
