"""Timestamp and leakage policy for prematch features."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any


class LeakageStatus(str, Enum):
    SAFE_PREMATCH = "SAFE_PREMATCH"
    FUTURE_SNAPSHOT_ONLY = "FUTURE_SNAPSHOT_ONLY"
    POST_MATCH_ONLY = "POST_MATCH_ONLY"
    LIVE_ONLY = "LIVE_ONLY"
    TIMESTAMP_PROVENANCE_INSUFFICIENT = "TIMESTAMP_PROVENANCE_INSUFFICIENT"
    REJECTED = "REJECTED"


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_prediction_cutoff(kickoff_utc: str, *, hours_before: float = 3.0) -> str:
    ko = _parse_utc(kickoff_utc)
    if ko is None:
        return utc_now_iso()
    from datetime import timedelta

    return (ko - timedelta(hours=hours_before)).isoformat()


def classify_timing(
    *,
    feature_available_at_utc: str | None,
    fetched_at_utc: str | None,
    prediction_cutoff_utc: str,
    kickoff_utc: str,
    is_live_upcoming: bool,
    is_realized_match_xg: bool = False,
    is_pressure: bool = False,
    is_post_match_stats: bool = False,
) -> LeakageStatus:
    if is_realized_match_xg:
        return LeakageStatus.POST_MATCH_ONLY
    if is_pressure:
        return LeakageStatus.LIVE_ONLY
    if is_post_match_stats:
        return LeakageStatus.POST_MATCH_ONLY

    avail = _parse_utc(feature_available_at_utc or fetched_at_utc)
    cutoff = _parse_utc(prediction_cutoff_utc)
    kickoff = _parse_utc(kickoff_utc)
    if cutoff is None or kickoff is None:
        return LeakageStatus.TIMESTAMP_PROVENANCE_INSUFFICIENT

    if avail is None:
        if is_live_upcoming:
            return LeakageStatus.FUTURE_SNAPSHOT_ONLY
        return LeakageStatus.TIMESTAMP_PROVENANCE_INSUFFICIENT

    if avail > cutoff:
        return LeakageStatus.REJECTED
    if cutoff >= kickoff:
        return LeakageStatus.REJECTED
    if avail > kickoff:
        return LeakageStatus.POST_MATCH_ONLY

    return LeakageStatus.SAFE_PREMATCH


def admissible_for_store(status: LeakageStatus, *, allow_future_snapshot: bool = True) -> bool:
    if status == LeakageStatus.SAFE_PREMATCH:
        return True
    if allow_future_snapshot and status == LeakageStatus.FUTURE_SNAPSHOT_ONLY:
        return True
    return False


def rolling_xg_cutoff_ok(*, source_fixture_kickoff: str, target_kickoff: str) -> bool:
    src = _parse_utc(source_fixture_kickoff)
    tgt = _parse_utc(target_kickoff)
    if src is None or tgt is None:
        return False
    return src < tgt
