"""Parses openWB's DETAILED log format into structured rows.

Format (see openWB/core packages/helpermodules/logger.py):
    "%(asctime)s - {%(name)s:%(lineno)s} - {%(levelname)s:%(threadName)s} - %(message)s"

Lines that don't match (e.g. traceback frames spilling across multiple lines)
are "continuations": they inherit timestamp/logger/level/thread from the
most recent matched line in the same batch, and are stored verbatim.

Timestamps are kept naive (no timezone), exactly as openWB's asctime writes
them -- the device's own wall-clock time, with no conversion applied. The DB
column is a plain TIMESTAMP for the same reason.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TypedDict

_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - "
    r"\{(?P<name>[^:]*):(?P<lineno>\d+)\} - "
    r"\{(?P<level>[A-Z]+):(?P<thread>[^}]*)\} - "
    r"(?P<message>.*)$"
)


class ParsedLine(TypedDict):
    ts: datetime
    logger_name: str | None
    line_no: int | None
    level: str | None
    thread: str | None
    message: str
    raw: str
    is_continuation: bool


def parse_line(raw: str, previous: ParsedLine | None) -> ParsedLine:
    match = _LINE_RE.match(raw)
    if match:
        ts = datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S,%f")
        return {
            "ts": ts,
            "logger_name": match.group("name") or None,
            "line_no": int(match.group("lineno")),
            "level": match.group("level"),
            "thread": match.group("thread") or None,
            "message": match.group("message"),
            "raw": raw,
            "is_continuation": False,
        }

    base = previous or {}
    return {
        # Only hit when the very first line ever ingested has no timestamp,
        # which shouldn't happen in practice.
        "ts": base.get("ts", datetime.now()),
        "logger_name": base.get("logger_name"),
        "line_no": base.get("line_no"),
        "level": base.get("level"),
        "thread": base.get("thread"),
        "message": raw,
        "raw": raw,
        "is_continuation": True,
    }
