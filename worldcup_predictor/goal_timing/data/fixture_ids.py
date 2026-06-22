"""Fixture ID validation for goal-timing data paths."""

from __future__ import annotations


def is_valid_fixture_id(fixture_id: int | str | None) -> bool:
    """True when fixture_id is a positive integer suitable for API-Football calls."""
    if fixture_id is None:
        return False
    try:
        fid = int(fixture_id)
    except (TypeError, ValueError):
        return False
    return fid > 0
