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


_OPENWB_INFO_RE = {
    "version": re.compile(r"'version': '([^']*)'"),
    "current_branch": re.compile(r"'current_branch': '([^']*)'"),
    "current_commit": re.compile(r"'current_commit': '([^']*)'"),
    "hostname": re.compile(r"'hostname': '([^']*)'"),
}
_COMMIT_HASH_RE = re.compile(r"\[([0-9a-f]+)\]")


def parse_openwb_info(message: str) -> dict[str, str] | None:
    """Best-effort extraction of openWB's own version/branch/commit/hostname
    from the full internal config dict it periodically logs to the main
    log (a Python repr of a plain dict, not JSON). Distinguished from the
    many *other* lines that also happen to contain a 'version' key --
    each chargepoint/inverter reports its own firmware version in a
    differently-shaped dataclass repr (`version='...'`, no quoted key) --
    by requiring both 'hostname' and 'current_commit' markers, which only
    ever appear together on this one line.

    Returns None if the line doesn't match or any expected field is
    missing. openWB's internal repr isn't a stable/versioned API (still
    on an alpha branch as of writing), so failing quietly here -- rather
    than raising -- is the point: a future openWB release reshaping this
    dict should just stop populating this info, not break the fetcher."""
    if "'hostname':" not in message or "'current_commit':" not in message:
        return None
    result: dict[str, str] = {}
    for key, pattern in _OPENWB_INFO_RE.items():
        match = pattern.search(message)
        if not match:
            return None
        result[key] = match.group(1)
    commit_hash = _COMMIT_HASH_RE.search(result["current_commit"])
    if commit_hash:
        result["current_commit_short"] = commit_hash.group(1)
    return result


def continuation_ratio(rows: list[ParsedLine]) -> float:
    """Fraction of already-parsed rows that came back as continuations,
    i.e. didn't match the expected format. Used by fetcher.py to flag a
    likely log_catalog.py format mismatch for a source -- occasional
    legitimate multi-line content (tracebacks etc.) only ever accounts for
    a small fraction of a batch, whereas a genuine mismatch between a
    source's declared and actual format fails to match almost every line,
    batch after batch."""
    if not rows:
        return 0.0
    return sum(1 for r in rows if r["is_continuation"]) / len(rows)
