"""Snapshot window classification (hours to kickoff)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.research.ecse_timing_experiment.constants import (
    EARLY_HOURS,
    LATE_HOURS,
    MID_HOURS,
    TZ_NAME,
)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_vienna(value: str | datetime | None, tz_name: str = TZ_NAME) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        dt = parse_dt(value)
    if not dt:
        return ""
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M %Z")


def hours_to_kickoff(kickoff_utc: str | None, as_of: datetime | None = None) -> float | None:
    ko = parse_dt(kickoff_utc)
    if not ko:
        return None
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (ko - now).total_seconds() / 3600.0


def classify_window(snapshot_class: str, hours: float | None) -> str:
    """Return IN_WINDOW / TOO_EARLY / TOO_LATE label for the snapshot class."""
    sc = str(snapshot_class or "").upper()
    if hours is None:
        return f"{sc}_UNKNOWN_HOURS"
    if sc == "EARLY":
        lo, hi = EARLY_HOURS
        prefix = "EARLY"
    elif sc == "MID":
        lo, hi = MID_HOURS
        prefix = "MID"
    elif sc == "LATE":
        lo, hi = LATE_HOURS
        prefix = "LATE"
    else:
        return "UNKNOWN_CLASS"
    if lo <= hours <= hi:
        return f"{prefix}_IN_WINDOW"
    if hours > hi:
        return f"{prefix}_TOO_EARLY"
    return f"{prefix}_TOO_LATE"


def window_meta(snapshot_class: str, kickoff_utc: str | None, as_of: datetime | None = None) -> dict[str, Any]:
    h = hours_to_kickoff(kickoff_utc, as_of=as_of)
    return {
        "hours_to_kickoff": None if h is None else round(h, 4),
        "window_classification": classify_window(snapshot_class, h),
        "target_window": {
            "EARLY": list(EARLY_HOURS),
            "MID": list(MID_HOURS),
            "LATE": list(LATE_HOURS),
        }.get(str(snapshot_class).upper()),
    }
