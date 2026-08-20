"""Pure, side-effect-free helpers for merging fetched log content.

Kept separate from fetcher.py so the tricky overlap/rotation logic can be
unit tested without any HTTP or database involved.
"""
from __future__ import annotations


def find_overlap_end(tail: list[str], content_lines: list[str]) -> int | None:
    """Find where `tail` (a known suffix we've already stored) reappears in
    `content_lines`, searching from the end for efficiency. Returns the index
    right after the match (i.e. content_lines[idx:] is new), or None if the
    tail isn't found anywhere in content_lines (rotation/gap)."""
    if not tail:
        return 0
    n, m = len(content_lines), len(tail)
    for start in range(n - m, -1, -1):
        if content_lines[start:start + m] == tail:
            return start + m
    return None


def split_new_lines(previous_tail: list[str], new_content: str) -> tuple[list[str], bool]:
    """Given the tail of lines we already saved, and the freshly fetched
    content, return (new_lines, gap_detected).

    gap_detected is True when previous_tail could not be located anywhere in
    new_content, meaning the log rotated (or was truncated) between polls and
    the caller should try to recover the missing lines from backup files.
    """
    content_lines = new_content.splitlines()
    if not previous_tail:
        return content_lines, False
    end = find_overlap_end(previous_tail, content_lines)
    if end is None:
        return content_lines, True
    return content_lines[end:], False


def assemble_backfill(older_contents: list[str], latest_content: str) -> list[str]:
    """Concatenates rotated backup contents (oldest first) with the current
    file's content, for seeding history on a source's very first-ever fetch
    -- so pre-existing rotated logs aren't silently skipped."""
    lines: list[str] = []
    for content in older_contents:
        lines.extend(content.splitlines())
    lines.extend(latest_content.splitlines())
    return lines


def stitch_gap(
    previous_tail: list[str], backup_content: str, latest_content: str
) -> list[str] | None:
    """Try to recover lines lost to a rotation using one backup file.

    If `previous_tail` is found inside `backup_content`, everything in the
    backup after that point plus all of `latest_content` is the recovered,
    gap-free sequence. Returns None if the tail isn't in this backup either
    (caller should try an older backup).
    """
    backup_lines = backup_content.splitlines()
    end = find_overlap_end(previous_tail, backup_lines)
    if end is None:
        return None
    return backup_lines[end:] + latest_content.splitlines()
