"""Polls the openWB ramdisk log and inserts new, gap-free lines into
TimescaleDB. Designed to run as a background task inside the web process
(see main.py) but fetch_once() can also be called standalone.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from .config import settings
from .db import get_pool, get_state, set_state
from .log_merge import split_new_lines, stitch_gap
from .log_parse import parse_line

logger = logging.getLogger("openwb_logger.fetcher")


@dataclass
class FetcherStatus:
    last_fetch_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_lines_added: int = 0
    total_gaps_detected: int = 0
    total_gaps_recovered: int = 0


class Fetcher:
    def __init__(self) -> None:
        self.status = FetcherStatus()

    async def _get(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url, timeout=settings.http_timeout_seconds)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            logger.warning("Fetching %s failed: %s", url, exc)
            return None

    async def fetch_once(self) -> None:
        self.status.last_fetch_at = datetime.now().isoformat(timespec="seconds")
        pool = get_pool()
        try:
            async with httpx.AsyncClient() as client:
                content = await self._get(client, settings.log_url)
                if content is None:
                    self.status.last_error = f"could not reach {settings.log_url}"
                    return

                previous_tail: list[str] = await get_state(pool, "tail", default=[])
                new_lines, gap = split_new_lines(previous_tail, content)

                if gap:
                    self.status.total_gaps_detected += 1
                    logger.info("Gap detected between polls, attempting recovery from backups")
                    recovered = await self._recover_gap(client, previous_tail, content)
                    if recovered is not None:
                        new_lines = recovered
                        self.status.total_gaps_recovered += 1
                    else:
                        logger.warning(
                            "Could not recover gap from any of the %d backup files; "
                            "some log lines were likely lost. Consider a shorter "
                            "FETCH_INTERVAL_SECONDS.",
                            settings.backup_count,
                        )
                        marker = "*** openwb-logger: gap detected, some lines may be missing ***"
                        new_lines = [marker] + new_lines

                if new_lines:
                    await self._insert_lines(pool, new_lines)
                    all_lines = (previous_tail + new_lines) if not gap else new_lines
                    await set_state(pool, "tail", all_lines[-settings.tail_window:])

                self.status.last_lines_added = len(new_lines)
                self.status.last_success_at = self.status.last_fetch_at
                self.status.last_error = None
        except Exception as exc:  # keep the background loop alive no matter what
            logger.exception("Unexpected error during fetch")
            self.status.last_error = str(exc)

    async def _recover_gap(
        self, client: httpx.AsyncClient, previous_tail: list[str], latest_content: str,
    ) -> list[str] | None:
        for n in range(1, settings.backup_count + 1):
            backup = await self._get(client, settings.backup_url(n))
            if backup is None:
                continue
            recovered = stitch_gap(previous_tail, backup, latest_content)
            if recovered is not None:
                return recovered
        return None

    async def _insert_lines(self, pool, lines: list[str]) -> None:
        previous = None
        rows = []
        for raw in lines:
            parsed = parse_line(raw, previous)
            previous = parsed
            rows.append(parsed)
        async with pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO log_lines "
                "(ts, logger_name, line_no, level, thread, message, raw, is_continuation) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                [
                    (
                        r["ts"], r["logger_name"], r["line_no"], r["level"],
                        r["thread"], r["message"], r["raw"], r["is_continuation"],
                    )
                    for r in rows
                ],
            )


fetcher = Fetcher()
