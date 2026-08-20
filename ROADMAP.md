# Roadmap

Loose notes on where this is headed, not a commitment. Reorder freely —
open an issue or just start working if something here matters to you.

## Done

- [x] Poll openWB's `main.log`, gap-free merge with rotation recovery
- [x] Structured storage in TimescaleDB, native retention policy
- [x] Web UI: browse by day, live-tail, filter, search, export
- [x] Multi log-source support (chargelog, mqtt, smarthome, soc, ...)
- [x] Runtime-configurable settings (location, sources, retention,
      interval) via the UI, no restart needed
- [x] Light/dark/system theme

## Next

- [ ] Authentication / access control for the web UI (currently none —
      LAN-only by convention, see DEPLOYMENT.md)
- [ ] `pg_trgm` index on `raw` for faster search once log volume grows
      large enough for a plain `ILIKE` scan to matter
- [ ] Per-source retention (right now retention is global across all
      collected logs)
- [ ] Surface parse failures/unexpected formats in the UI instead of only
      the container logs

## Someday / maybe

- [ ] Simple chart/dashboard view (e.g. charge sessions over time, error
      rate) — low priority, out of scope for a "logger"
- [ ] Alerting on ERROR-level lines (webhook/notification)
- [ ] Multi-openWB support (more than one device polled into the same DB)
- [ ] Home Assistant integration
