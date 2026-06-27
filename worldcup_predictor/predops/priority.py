"""PredOps kickoff priority bands — Phase A15."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, hours_until_kickoff

PRIORITY_KICKOFF_3H = 1
PRIORITY_KICKOFF_12H = 2
PRIORITY_KICKOFF_24H = 3
PRIORITY_KICKOFF_72H = 4
PRIORITY_KICKOFF_7D = 5
PRIORITY_LATER = 6


def priority_band_for_kickoff(kickoff_utc: datetime | None, *, now: datetime | None = None) -> int:
    hours = hours_until_kickoff(kickoff_utc, now=now)
    if hours is None:
        return PRIORITY_KICKOFF_7D
    if hours < 0:
        return PRIORITY_LATER
    if hours <= 3:
        return PRIORITY_KICKOFF_3H
    if hours <= 12:
        return PRIORITY_KICKOFF_12H
    if hours <= 24:
        return PRIORITY_KICKOFF_24H
    if hours <= 72:
        return PRIORITY_KICKOFF_72H
    if hours <= 24 * 7:
        return PRIORITY_KICKOFF_7D
    return PRIORITY_LATER


def priority_label(band: int) -> str:
    return {
        PRIORITY_KICKOFF_3H: "<3h",
        PRIORITY_KICKOFF_12H: "<12h",
        PRIORITY_KICKOFF_24H: "<24h",
        PRIORITY_KICKOFF_72H: "<72h",
        PRIORITY_KICKOFF_7D: "<7d",
        PRIORITY_LATER: "later",
    }.get(band, "unknown")


def sort_fixtures_by_priority(fixtures: list[dict[str, Any]], *, now: datetime | None = None) -> list[dict[str, Any]]:
    def _key(row: dict[str, Any]) -> tuple:
        kick = _parse_dt(row.get("kickoff_utc") or row.get("match_date"))
        band = priority_band_for_kickoff(kick, now=now)
        kick_ts = kick.isoformat() if kick else "9999"
        return (band, kick_ts)

    return sorted(fixtures, key=_key)
