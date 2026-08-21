# Roadmap

Loose notes on where this is headed, not a commitment. Reorder freely —
open an issue or just start working if something here matters to you.

## Done

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

## Next

- [ ] All-in-one image: bundle the app and TimescaleDB into a single
      container/image for simpler distribution, instead of the current
      two-service docker-compose setup. The infra-vs-runtime-settings split
      (`app/config.py` vs `app/runtime_settings.py`) was done specifically
      to make this straightforward later — `DATABASE_URL` can collapse to
      a fixed localhost value and everything else is already configured
      from inside the app, not env vars.

## Someday / maybe

- [ ] MCP server: expose the collected logs (search, tail, export) as MCP
      tools/resources so an AI assistant (e.g. Claude) can query openWB's
      history directly instead of through the web UI
- [ ] Simple chart/dashboard view (e.g. charge sessions over time, error
      rate) — low priority, out of scope for a "logger"
- [ ] Alerting on ERROR-level lines (webhook/notification)
- [ ] Multi-openWB support (more than one device polled into the same DB)
- [ ] Home Assistant integration
