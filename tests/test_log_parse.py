import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.log_parse import continuation_ratio, parse_line

DETAILED_LINE = (
    "2026-08-20 14:32:01,123 - {chargepoint.py:88} - {INFO:MainThread} - Ladung gestartet"
)


def test_parse_detailed_line():
    result = parse_line(DETAILED_LINE, previous=None)
    assert result["ts"] == datetime(2026, 8, 20, 14, 32, 1, 123000)
    assert result["logger_name"] == "chargepoint.py"
    assert result["line_no"] == 88
    assert result["level"] == "INFO"
    assert result["thread"] == "MainThread"
    assert result["message"] == "Ladung gestartet"
    assert result["raw"] == DETAILED_LINE
    assert result["is_continuation"] is False


def test_continuation_line_inherits_context_from_previous():
    previous = parse_line(DETAILED_LINE, previous=None)
    traceback_line = "  File \"chargepoint.py\", line 88, in start"
    result = parse_line(traceback_line, previous=previous)
    assert result["ts"] == previous["ts"]
    assert result["logger_name"] == "chargepoint.py"
    assert result["level"] == "INFO"
    assert result["message"] == traceback_line
    assert result["is_continuation"] is True


def test_continuation_line_with_no_previous_context():
    result = parse_line("some stray line", previous=None)
    assert result["logger_name"] is None
    assert result["is_continuation"] is True


SHORT_LINE = "2026-08-20 14:32:01,123 - Ladevorgang beendet, 3.2 kWh geladen"


def test_parse_short_line():
    result = parse_line(SHORT_LINE, previous=None, log_format="short")
    assert result["ts"] == datetime(2026, 8, 20, 14, 32, 1, 123000)
    assert result["logger_name"] is None
    assert result["line_no"] is None
    assert result["level"] is None
    assert result["thread"] is None
    assert result["message"] == "Ladevorgang beendet, 3.2 kWh geladen"
    assert result["raw"] == SHORT_LINE
    assert result["is_continuation"] is False


def test_short_continuation_inherits_timestamp_only():
    previous = parse_line(SHORT_LINE, previous=None, log_format="short")
    result = parse_line("  extra detail line", previous=previous, log_format="short")
    assert result["ts"] == previous["ts"]
    assert result["is_continuation"] is True


def test_continuation_ratio_empty_batch():
    assert continuation_ratio([]) == 0.0


def test_continuation_ratio_all_matched():
    previous = None
    rows = []
    for _ in range(5):
        previous = parse_line(DETAILED_LINE, previous=previous)
        rows.append(previous)
    assert continuation_ratio(rows) == 0.0


def test_continuation_ratio_mixed_batch():
    matched = parse_line(DETAILED_LINE, previous=None)
    unmatched = parse_line("stray traceback line", previous=matched)
    assert continuation_ratio([matched, unmatched]) == 0.5


def test_continuation_ratio_all_unmatched():
    previous = parse_line("garbled line 1", previous=None)
    rows = [previous]
    for i in range(2, 6):
        previous = parse_line(f"garbled line {i}", previous=previous)
        rows.append(previous)
    assert continuation_ratio(rows) == 1.0
