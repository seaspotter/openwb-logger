import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.log_parse import parse_line

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
