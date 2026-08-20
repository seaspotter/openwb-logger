# Roadmap

Loose notes on where this is headed, not a commitment. Reorder freely —
open an issue or just start working if something here matters to you.

## Done

- [x] Poll openWB's `main.log`, gap-free merge with rotation recovery
- [x] Structured storage in TimescaleDB, native retention policy
- [x] Web UI: browse by day, live-tail, filter, search, export
- [x] Multi log-source support (chargelog, mqtt, smarthome, soc, ...)
- [x] Runtime-configurable settings (location, sources, retention,
      interval) via the UI, no restart, no environment variables
- [x] Light/dark/system theme, UI in German
- [x] Manual "Jetzt abrufen" (fetch now) trigger + last-fetch timestamp in
      the UI, alongside the scheduled poll

## Next

- [ ] All-in-one image: bundle the app and TimescaleDB into a single
      container/image for simpler distribution, instead of the current
      two-service docker-compose setup. The infra-vs-runtime-settings split
      (`app/config.py` vs `app/runtime_settings.py`) was done specifically
      to make this straightforward later — `DATABASE_URL` can collapse to
      a fixed localhost value and everything else is already configured
      from inside the app, not env vars.
- [ ] Authentication / access control for the web UI (currently none —
      LAN-only by convention, see DEPLOYMENT.md)
- [ ] `pg_trgm` index on `raw` for faster search once log volume grows
      large enough for a plain `ILIKE` scan to matter
- [ ] Per-source retention and per-source poll interval (right now both
      are global across all collected logs)
- [ ] Surface parse failures/unexpected formats in the UI instead of only
      the container logs

## Someday / maybe

- [ ] MCP server: expose the collected logs (search, tail, export) as MCP
      tools/resources so an AI assistant (e.g. Claude) can query openWB's
      history directly instead of through the web UI
- [ ] Simple chart/dashboard view (e.g. charge sessions over time, error
      rate) — low priority, out of scope for a "logger"
- [ ] Alerting on ERROR-level lines (webhook/notification)
- [ ] Multi-openWB support (more than one device polled into the same DB)
- [ ] Home Assistant integration
