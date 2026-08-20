import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.log_merge import find_overlap_end, split_new_lines, stitch_gap


def test_split_new_lines_no_previous_tail_returns_everything():
    lines, gap = split_new_lines([], "a\nb\nc")
    assert lines == ["a", "b", "c"]
    assert gap is False


def test_split_new_lines_returns_only_new_content():
    previous_tail = ["a", "b"]
    new_content = "a\nb\nc\nd"
    lines, gap = split_new_lines(previous_tail, new_content)
    assert lines == ["c", "d"]
    assert gap is False


def test_split_new_lines_no_new_content_yet():
    previous_tail = ["a", "b"]
    new_content = "a\nb"
    lines, gap = split_new_lines(previous_tail, new_content)
    assert lines == []
    assert gap is False


def test_split_new_lines_detects_gap_when_tail_missing():
    previous_tail = ["x", "y"]
    new_content = "c\nd\ne"
    lines, gap = split_new_lines(previous_tail, new_content)
    assert lines == ["c", "d", "e"]
    assert gap is True


def test_find_overlap_end_matches_last_occurrence():
    tail = ["b", "c"]
    content = ["a", "b", "c", "b", "c", "d"]
    assert find_overlap_end(tail, content) == 5


def test_stitch_gap_recovers_missing_lines_from_backup():
    previous_tail = ["a", "b"]
    backup_content = "a\nb\nc\nd"
    latest_content = "e\nf"
    result = stitch_gap(previous_tail, backup_content, latest_content)
    assert result == ["c", "d", "e", "f"]


def test_stitch_gap_returns_none_when_tail_not_in_backup():
    previous_tail = ["x", "y"]
    backup_content = "a\nb\nc"
    latest_content = "d\ne"
    assert stitch_gap(previous_tail, backup_content, latest_content) is None
