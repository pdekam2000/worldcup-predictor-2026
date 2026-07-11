"""ODDS-FRESHNESS-1 — Central odds freshness policy (no scoring changes)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from worldcup_predictor.odds.timestamp_normalization import (
    parse_timestamp_utc,
    timestamp_age_hours,
)

PHASE = "ODDS-FRESHNESS-1"

KNOCKOUT_STALE_HOURS = 6.0
NORMAL_STALE_HOURS = 12.0
LOW_PRIORITY_STALE_HOURS = 24.0


class FreshnessStatus(str, Enum):
    FRESH_ODDS = "FRESH_ODDS"
    STALE_ODDS = "STALE_ODDS"
    ODDS_FRESHNESS_UNKNOWN = "ODDS_FRESHNESS_UNKNOWN"
    ODDS_MISSING = "ODDS_MISSING"
    REQUIRES_FRESH_ODDS = "REQUIRES_FRESH_ODDS"


def parse_timestamp(value: str | None) -> datetime | None:
    """Backward-compatible alias for central odds timestamp parser."""
    return parse_timestamp_utc(value)


def is_knockout_match(*, round_name: str | None = None, status: str | None = None) -> bool:
    stage = str(round_name or "").lower()
    if any(k in stage for k in ("round of", "knockout", "quarter", "semi", "final", "play-off", "playoff")):
        return True
    return str(status or "").upper() in {"AET", "PEN"}


def is_low_priority_match(*, kickoff_utc: str | None, reference: datetime | None = None) -> bool:
    ko = parse_timestamp(kickoff_utc)
    if ko is None:
        return False
    ref = reference or datetime.now(timezone.utc)
    return (ko - ref).total_seconds() / 3600.0 > 72.0


def stale_threshold_hours(
    *,
    knockout: bool = False,
    low_priority: bool = False,
    kickoff_utc: str | None = None,
    reference_at: datetime | None = None,
    allow_post_kickoff_live: bool = False,
) -> float:
    """Hours threshold; prefers kickoff-aware TTL when kickoff_utc is provided."""
    if kickoff_utc:
        ttl_sec = get_allowed_odds_ttl_seconds(
            kickoff_utc,
            reference_at,
            allow_post_kickoff_live=allow_post_kickoff_live,
        )
        if ttl_sec is None:
            return 0.0
        return ttl_sec / 3600.0
    if knockout:
        return KNOCKOUT_STALE_HOURS
    if low_priority:
        return LOW_PRIORITY_STALE_HOURS
    return NORMAL_STALE_HOURS


def get_allowed_odds_ttl_seconds(
    kickoff_utc: str | None,
    now_utc: datetime | str | None = None,
    *,
    allow_post_kickoff_live: bool = False,
) -> int | None:
    """Dynamic prematch TTL by time-to-kickoff. None => odds invalid (post-kickoff)."""
    ko = parse_timestamp_utc(kickoff_utc)
    if ko is None:
        return int(NORMAL_STALE_HOURS * 3600)
    if isinstance(now_utc, datetime):
        ref = now_utc.astimezone(timezone.utc)
    else:
        ref = parse_timestamp_utc(now_utc) if now_utc else datetime.now(timezone.utc)
    if ref is None:
        ref = datetime.now(timezone.utc)
    hours_to_ko = (ko - ref).total_seconds() / 3600.0
    if hours_to_ko < 0:
        return 600 if allow_post_kickoff_live else None
    if hours_to_ko > 24:
        return 6 * 3600
    if hours_to_ko > 6:
        return 2 * 3600
    if hours_to_ko > 1:
        return 30 * 60
    return 10 * 60


def calculate_odds_age_hours(
    odds_snapshot_at: str | None,
    *,
    reference_at: str | datetime | None = None,
) -> float | None:
    if isinstance(reference_at, datetime):
        ref = reference_at.astimezone(timezone.utc)
    else:
        ref = parse_timestamp_utc(reference_at) if reference_at else datetime.now(timezone.utc)
    if ref is None:
        ref = datetime.now(timezone.utc)
    return timestamp_age_hours(odds_snapshot_at, now_utc=ref)


@dataclass
class FreshnessClassification:
    status: FreshnessStatus
    odds_age_hours: float | None
    stale_threshold_hours: float
    requires_fresh_odds: bool
    stale_odds: bool
    odds_snapshot_at: str | None = None
    reference_at: str | None = None
    odds_source: str | None = None
    priority_tier: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "freshness_flag": self.status.value,
            "odds_freshness_status": self.status.value,
            "odds_age_hours": self.odds_age_hours,
            "stale_threshold_hours": self.stale_threshold_hours,
            "requires_fresh_odds": self.requires_fresh_odds,
            "stale_odds": self.stale_odds,
            "odds_snapshot_at": self.odds_snapshot_at,
            "reference_at": self.reference_at,
            "odds_source": self.odds_source,
            "priority_tier": self.priority_tier,
        }


def classify_odds_freshness(
    *,
    odds_snapshot_at: str | None,
    reference_at: str | datetime | None = None,
    kickoff_utc: str | None = None,
    knockout: bool = False,
    low_priority: bool = False,
    odds_source: str | None = None,
    has_odds: bool | None = None,
    allow_post_kickoff_live: bool = False,
    freshness_reason: str | None = None,
) -> FreshnessClassification:
    ref_dt = reference_at if isinstance(reference_at, datetime) else parse_timestamp_utc(reference_at)
    if ref_dt is None and reference_at is None:
        ref_dt = datetime.now(timezone.utc)
    threshold = stale_threshold_hours(
        knockout=knockout,
        low_priority=low_priority,
        kickoff_utc=kickoff_utc,
        reference_at=ref_dt,
        allow_post_kickoff_live=allow_post_kickoff_live,
    )
    tier = "knockout" if knockout else ("low_priority" if low_priority else "normal")
    if kickoff_utc and get_allowed_odds_ttl_seconds(
        kickoff_utc, ref_dt, allow_post_kickoff_live=allow_post_kickoff_live
    ) is None and not (has_odds or odds_snapshot_at):
        return FreshnessClassification(
            status=FreshnessStatus.ODDS_MISSING,
            odds_age_hours=None,
            stale_threshold_hours=0.0,
            requires_fresh_odds=True,
            stale_odds=True,
            odds_snapshot_at=odds_snapshot_at,
            reference_at=str(reference_at) if reference_at else None,
            odds_source=odds_source,
            priority_tier=tier,
        )
    if kickoff_utc and get_allowed_odds_ttl_seconds(
        kickoff_utc, ref_dt, allow_post_kickoff_live=allow_post_kickoff_live
    ) is None and (has_odds or odds_snapshot_at):
        return FreshnessClassification(
            status=FreshnessStatus.STALE_ODDS,
            odds_age_hours=calculate_odds_age_hours(odds_snapshot_at, reference_at=reference_at),
            stale_threshold_hours=0.0,
            requires_fresh_odds=True,
            stale_odds=True,
            odds_snapshot_at=odds_snapshot_at,
            reference_at=str(reference_at) if reference_at else None,
            odds_source=odds_source,
            priority_tier=tier,
        )

    if has_odds is False or (has_odds is None and not odds_snapshot_at):
        return FreshnessClassification(
            status=FreshnessStatus.ODDS_MISSING,
            odds_age_hours=None,
            stale_threshold_hours=threshold,
            requires_fresh_odds=True,
            stale_odds=True,
            odds_snapshot_at=odds_snapshot_at,
            reference_at=str(reference_at) if reference_at else None,
            odds_source=odds_source,
            priority_tier=tier,
        )

    age = calculate_odds_age_hours(odds_snapshot_at, reference_at=reference_at)
    if age is None:
        return FreshnessClassification(
            status=FreshnessStatus.ODDS_FRESHNESS_UNKNOWN,
            odds_age_hours=None,
            stale_threshold_hours=threshold,
            requires_fresh_odds=True,
            stale_odds=False,
            odds_snapshot_at=odds_snapshot_at,
            reference_at=str(reference_at) if reference_at else None,
            odds_source=odds_source,
            priority_tier=tier,
        )

    stale = age > threshold
    if stale:
        status = FreshnessStatus.STALE_ODDS
    else:
        status = FreshnessStatus.FRESH_ODDS

    return FreshnessClassification(
        status=status,
        odds_age_hours=age,
        stale_threshold_hours=threshold,
        requires_fresh_odds=stale or status == FreshnessStatus.ODDS_FRESHNESS_UNKNOWN,
        stale_odds=stale,
        odds_snapshot_at=odds_snapshot_at,
        reference_at=str(reference_at) if reference_at else None,
        odds_source=odds_source,
        priority_tier=tier,
    )


def should_refresh_odds(classification: FreshnessClassification | dict[str, Any]) -> bool:
    if isinstance(classification, FreshnessClassification):
        status = classification.status
    else:
        status = FreshnessStatus(classification.get("freshness_flag") or classification.get("odds_freshness_status") or "ODDS_FRESHNESS_UNKNOWN")
    return status in {
        FreshnessStatus.STALE_ODDS,
        FreshnessStatus.ODDS_MISSING,
        FreshnessStatus.REQUIRES_FRESH_ODDS,
    }


def explain_odds_freshness(classification: FreshnessClassification | dict[str, Any]) -> str:
    if isinstance(classification, dict):
        flag = classification.get("freshness_flag") or classification.get("odds_freshness_status")
        age = classification.get("odds_age_hours")
        threshold = classification.get("stale_threshold_hours")
        tier = classification.get("priority_tier", "normal")
    else:
        flag = classification.status.value
        age = classification.odds_age_hours
        threshold = classification.stale_threshold_hours
        tier = classification.priority_tier

    if flag == FreshnessStatus.FRESH_ODDS.value:
        return f"Odds are fresh ({age}h old, threshold {threshold}h for {tier})."
    if flag == FreshnessStatus.STALE_ODDS.value:
        return f"Odds are stale ({age}h old > {threshold}h threshold for {tier}). Refresh recommended."
    if flag == FreshnessStatus.ODDS_MISSING.value:
        return "No odds snapshot stored for this fixture. Refresh required before high-confidence use."
    if flag == FreshnessStatus.REQUIRES_FRESH_ODDS.value:
        return "Fixture requires fresh odds before knockout/high-stakes prediction."
    return "Odds snapshot timestamp missing or unparseable; freshness unknown."


def build_prediction_freshness_metadata(
    classification: FreshnessClassification,
    *,
    odds_refresh_attempted: bool = False,
    odds_refresh_success: bool | None = None,
    odds_refresh_reason: str | None = None,
) -> dict[str, Any]:
    out = classification.to_dict()
    out["odds_refresh_attempted"] = odds_refresh_attempted
    out["odds_refresh_success"] = odds_refresh_success
    out["odds_refresh_reason"] = odds_refresh_reason
    out["explanation"] = explain_odds_freshness(classification)
    return out
