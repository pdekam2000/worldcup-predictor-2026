"""Canonical forward Correct Score snapshot windows with tolerances."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
    SNAPSHOT_WINDOWS,
    WINDOW_TOLERANCE,
)


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s[:32] if len(s) > 19 else s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def seconds_to_kickoff(fetched_at: datetime, kickoff: datetime) -> float:
    return (kickoff - fetched_at).total_seconds()


def classify_window(seconds_before_ko: float) -> str | None:
    """Map seconds-to-kickoff to a canonical window label (best match)."""
    if seconds_before_ko <= 0:
        return None  # at/after kickoff — reject
    # prefer more specific windows first
    for label in ("APPROX_1H", "APPROX_6H", "APPROX_24H", "FINAL_PREMATCH"):
        lo, hi = WINDOW_TOLERANCE[label]
        if lo is None or hi is None:
            continue
        if lo <= seconds_before_ko <= hi:
            return label
    # FINAL_PREMATCH already checked; FIRST_AVAILABLE is residual prematch
    if seconds_before_ko > 0:
        return "FIRST_AVAILABLE"
    return None


def window_allows(seconds_before_ko: float, window: str) -> bool:
    if seconds_before_ko <= 0:
        return False
    if window == "FIRST_AVAILABLE":
        return seconds_before_ko > 0
    lo, hi = WINDOW_TOLERANCE.get(window, (None, None))
    if lo is None or hi is None:
        return False
    return lo <= seconds_before_ko <= hi


def select_snapshot_for_window(
    lines: list[dict[str, Any]],
    *,
    kickoff: datetime,
    window: str,
) -> dict[str, Any] | None:
    """
    Pick nearest legitimate prematch snapshot for window.
    lines: dicts with fetched_at_utc, decimal_odds, selection, bookmaker_name, ...
    """
    candidates: list[tuple[float, dict]] = []
    for ln in lines:
        fetched = parse_utc(str(ln.get("fetched_at_utc") or ""))
        if not fetched:
            continue
        secs = seconds_to_kickoff(fetched, kickoff)
        if secs <= 0:
            continue
        if not window_allows(secs, window):
            continue
        # distance to nominal center
        if window == "APPROX_24H":
            target = 24 * 3600
        elif window == "APPROX_6H":
            target = 6 * 3600
        elif window == "APPROX_1H":
            target = 3600
        elif window == "FINAL_PREMATCH":
            target = 0  # prefer latest (smallest secs)
            candidates.append((secs, ln))
            continue
        else:
            target = secs
        candidates.append((abs(secs - target), ln))
    if not candidates:
        return None
    if window == "FINAL_PREMATCH":
        # smallest seconds_to_kickoff among allowed
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def group_lines_by_fetch(lines: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for ln in lines:
        key = f"{ln.get('fetched_at_utc')}|{ln.get('bookmaker_name')}|{ln.get('provider')}"
        out.setdefault(key, []).append(ln)
    return out


__all__ = [
    "SNAPSHOT_WINDOWS",
    "classify_window",
    "parse_utc",
    "seconds_to_kickoff",
    "select_snapshot_for_window",
    "window_allows",
    "group_lines_by_fetch",
]
