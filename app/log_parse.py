"""Parses openWB's log formats into structured rows.

openWB (see openWB/core packages/helpermodules/logger.py) writes each
logger in one of two formats:

  DETAILED: "%(asctime)s - {%(name)s:%(lineno)s} - {%(levelname)s:%(threadName)s} - %(message)s"
  SHORT:    "%(asctime)s - %(message)s"

Which format a given log uses is fixed per-source (see log_catalog.py), not
something detected line by line.

Lines that don't match the expected pattern (e.g. traceback frames spilling
across multiple lines) are "continuations": they inherit timestamp/logger/
level/thread from the most recent matched line in the same batch, and are
stored verbatim.

Timestamps are kept naive (no timezone), exactly as openWB's asctime writes
them -- the device's own wall-clock time, with no conversion applied. The DB
column is a plain TIMESTAMP for the same reason.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TypedDict

from .log_catalog import LogFormat

_DETAILED_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - "
    r"\{(?P<name>[^:]*):(?P<lineno>\d+)\} - "
    r"\{(?P<level>[A-Z]+):(?P<thread>[^}]*)\} - "
    r"(?P<message>.*)$"
)

_SHORT_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (?P<message>.*)$"
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


def _continuation(raw: str, previous: ParsedLine | None) -> ParsedLine:
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


def parse_line(
    raw: str, previous: ParsedLine | None, log_format: LogFormat = "detailed"
) -> ParsedLine:
    if log_format == "short":
        match = _SHORT_RE.match(raw)
        if not match:
            return _continuation(raw, previous)
        ts = datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S,%f")
        return {
            "ts": ts,
            "logger_name": None,
            "line_no": None,
            "level": None,
            "thread": None,
            "message": match.group("message"),
            "raw": raw,
            "is_continuation": False,
        }

    match = _DETAILED_RE.match(raw)
    if not match:
        return _continuation(raw, previous)
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
