# Roadmap

Loose notes on where this is headed, not a commitment. Reorder freely —
open an issue or just start working if something here matters to you.

## Done (v0.1.0)

- [x] Poll openWB's `main.log`, gap-free merge with rotation recovery
- [x] Structured storage in TimescaleDB, native retention policy
- [x] Web UI: browse by day, live-tail, filter, search, export
- [x] Multi log-source support (chargelog, mqtt, soc, internal chargepoint)
- [x] Runtime-configurable settings (location, sources, retention,
      interval) via the UI, no restart, no environment variables
- [x] Light/dark theme (system preference on first visit, then a plain
      toggle), UI in German
- [x] Manual "Jetzt abrufen" (fetch now) trigger + last-fetch timestamp in
      the UI, alongside the scheduled poll
- [x] Optional in-app self-update button (git pull + process restart,
      via a repo bind-mount onto the container's WORKDIR — no Docker
      socket, no rebuild)
- [x] Cursor/keyset-based paging (by `(ts, id)`) instead of `OFFSET/LIMIT`
      for day/Zeitraum views — paging cost no longer grows with depth
- [x] Surface parse failures/unexpected formats in the UI instead of only
      the container logs — a per-source "format warning" in the status
      bar (plus a container log warning) when an unusually high fraction
      of a batch doesn't match the source's declared format
- [x] MCP server: `search_logs`/`tail_logs`/`export_logs` tools plus an
      `openwb://sources` resource, mounted at `/mcp` alongside the web UI
      on the same port (Streamable HTTP transport, `mcp` pinned to its
      1.x line — 2.x's `starlette` requirement conflicts with `fastapi`)
- [x] Alerts indicator instead of a full webhook/notification system: a
      small "!" button/badge in the UI aggregating current errors/
      warnings (fetch failures, format-mismatch, gaps, ERROR-level lines)
      in one place, quiet by default — no popups, no external
      notifications, just something to check when you want to.

## Next

## Someday / maybe

- [ ] Multi-openWB support (more than one device polled into the same DB)
      — distant future, not currently planned work
