"""Polls each enabled openWB log and inserts new, gap-free lines into
TimescaleDB. Designed to run as a background task inside the web process
(see main.py) but fetch_once() can also be called standalone.

Which logs are enabled, where openWB is, and the poll interval are all
read fresh from runtime_settings on every cycle, so changes made through
the web UI take effect on the next poll without a restart.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from .db import apply_retention_policy, get_state, set_state
from .log_catalog import CATALOG
from .log_merge import assemble_backfill, split_new_lines, stitch_gap
from .log_parse import continuation_ratio, parse_line
from .runtime_settings import RuntimeSettings, defaults, get_settings

logger = logging.getLogger("openwb_logger.fetcher")

HTTP_TIMEOUT_SECONDS = 15

# Trailing raw lines kept (in the DB) per source to detect overlap/rotation
# between polls. Internal tuning, not user-facing settings.
TAIL_WINDOW = 50

# A batch where more than this fraction of lines don't match the source's
# expected format (log_catalog.py) is treated as a likely format mismatch
# rather than occasional legitimate multi-line content (tracebacks etc.) --
# see SourceStatus.format_mismatch_suspected and log_parse.continuation_ratio.
FORMAT_MISMATCH_RATIO_THRESHOLD = 0.5
# Batches smaller than this are too small for the ratio to be a reliable
# signal -- e.g. one 2-line traceback in an otherwise tiny batch would
# swing it wildly -- so the check is skipped below this size.
FORMAT_MISMATCH_MIN_BATCH = 10


@dataclass
class SourceStatus:
    last_lines_added: int = 0
    total_gaps_detected: int = 0
    total_gaps_recovered: int = 0
    last_error: str | None = None
    format_mismatch_suspected: bool = False


@dataclass
class FetcherStatus:
    last_fetch_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    sources: dict[str, SourceStatus] = field(default_factory=dict)


class Fetcher:
    def __init__(self) -> None:
        self.status = FetcherStatus()
        # Guards against a manual "fetch now" overlapping the scheduled poll
        # (or two manual clicks): both would otherwise read the same
        # per-source tail state concurrently and could double-insert lines.
        self._lock = asyncio.Lock()
        # apply_retention_policy() tears down and recreates TimescaleDB's own
        # retention job (remove_retention_policy + add_retention_policy) --
        # only worth doing when retention_days has actually changed, not on
        # every single poll cycle regardless. Re-applying it unconditionally
        # every cycle (as this used to do) churns the job constantly for no
        # reason, and risks tearing it down while a run is genuinely
        # mid-execution -- plausibly a contributing factor to a real
        # catalog-corruption bug diagnosed once already (see DEPLOYMENT.md).
        self._applied_retention_days: int | None = None

    async def _get(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            logger.warning("Fetching %s failed: %s", url, exc)
            return None

    async def fetch_once(self, pool) -> RuntimeSettings:
        """Runs one poll cycle across all enabled sources. Returns the
        runtime settings used, so the caller (the poll loop) can sleep for
        the current fetch_interval_seconds without a second DB round trip."""
        async with self._lock:
            self.status.last_fetch_at = datetime.now().isoformat(timespec="seconds")
            try:
                rt = await get_settings(pool)
                if rt["retention_days"] != self._applied_retention_days:
                    await apply_retention_policy(pool, rt["retention_days"])
                    self._applied_retention_days = rt["retention_days"]

                async with httpx.AsyncClient() as client:
                    for name in rt["enabled_sources"]:
                        if name not in CATALOG:
                            continue
                        await self._fetch_source(pool, client, name, rt)

                self.status.last_success_at = self.status.last_fetch_at
                self.status.last_error = None
                return rt
            except Exception as exc:  # keep the background loop alive no matter what
                logger.exception("Unexpected error during fetch")
                self.status.last_error = str(exc)
                return defaults()

    async def _fetch_source(self, pool, client, name: str, rt: RuntimeSettings) -> None:
        meta = CATALOG[name]
        url = f"{rt['openwb_base_url']}{rt['openwb_ramdisk_path']}/{name}.log"
        st = self.status.sources.setdefault(name, SourceStatus())

        content = await self._get(client, url)
        if content is None:
            st.last_error = f"could not reach {url}"
            return
        st.last_error = None

        tail_key = f"tail:{name}"
        stored_tail = await get_state(pool, tail_key, default=None)
        first_fetch = stored_tail is None
        previous_tail: list[str] = stored_tail or []
        gap = False

        if first_fetch:
            logger.info(
                "[%s] first-ever fetch for this source, backfilling from existing backups", name
            )
            new_lines = await self._backfill(client, url, content, meta["backup_count"])
        else:
            new_lines, gap = split_new_lines(previous_tail, content)

            if gap:
                st.total_gaps_detected += 1
                logger.info(
                    "[%s] gap detected between polls, attempting recovery from backups", name
                )
                recovered = await self._recover_gap(
                    client, previous_tail, content, url, meta["backup_count"]
                )
                if recovered is not None:
                    new_lines = recovered
                    st.total_gaps_recovered += 1
                else:
                    logger.warning(
                        "[%s] could not recover gap from any of the %d backup files; "
                        "some log lines were likely lost. Consider a shorter poll interval.",
                        name, meta["backup_count"],
                    )
                    marker = (
                        f"*** openwb-logger: gap detected in {name}, some lines may be missing ***"
                    )
                    new_lines = [marker] + new_lines

        if new_lines:
            ratio = await self._insert_lines(pool, name, meta["format"], new_lines)
            if len(new_lines) >= FORMAT_MISMATCH_MIN_BATCH:
                suspected = ratio > FORMAT_MISMATCH_RATIO_THRESHOLD
                if suspected and not st.format_mismatch_suspected:
                    logger.warning(
                        "[%s] %.0f%% of %d new lines didn't match the expected '%s' format -- "
                        "check the format declared in log_catalog.py for this source",
                        name, ratio * 100, len(new_lines), meta["format"],
                    )
                st.format_mismatch_suspected = suspected
            new_tail = (previous_tail + new_lines) if not gap else new_lines
            await set_state(pool, tail_key, new_tail[-TAIL_WINDOW:])

        st.last_lines_added = len(new_lines)

    async def _backfill(
        self, client: httpx.AsyncClient, url: str, latest_content: str, backup_count: int,
    ) -> list[str]:
        older_contents = []
        for n in range(backup_count, 0, -1):
            backup = await self._get(client, f"{url}.{n}")
            if backup is not None:
                older_contents.append(backup)
        return assemble_backfill(older_contents, latest_content)

    async def _recover_gap(
        self, client, previous_tail: list[str], latest_content: str, url: str, backup_count: int,
    ) -> list[str] | None:
        for n in range(1, backup_count + 1):
            backup = await self._get(client, f"{url}.{n}")
            if backup is None:
                continue
            recovered = stitch_gap(previous_tail, backup, latest_content)
            if recovered is not None:
                return recovered
        return None

    async def _insert_lines(self, pool, source: str, log_format: str, lines: list[str]) -> float:
        """Returns the fraction of `lines` that didn't match the expected
        format, for the caller to compare against
        FORMAT_MISMATCH_RATIO_THRESHOLD."""
        previous = None
        rows = []
        for raw in lines:
            parsed = parse_line(raw, previous, log_format=log_format)
            previous = parsed
            rows.append(parsed)
        async with pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO log_lines "
                "(ts, source, logger_name, line_no, level, thread, message, is_continuation) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                [
                    (
                        r["ts"], source, r["logger_name"], r["line_no"], r["level"],
                        r["thread"], r["message"], r["is_continuation"],
                    )
                    for r in rows
                ],
            )
        return continuation_ratio(rows)


fetcher = Fetcher()
