"""PredOps autonomous refresh policy — Phase A15 (orchestration TTL only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, hours_until_kickoff
from worldcup_predictor.prediction.engine_versions import PREDICTION_ENGINE_VERSION


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def refresh_interval_hours(kickoff_utc: datetime | None, *, now: datetime | None = None) -> float:
    """Hours between autonomous refreshes by kickoff proximity."""
    hours = hours_until_kickoff(kickoff_utc, now=now)
    if hours is None:
        return 24.0
    if hours < 0:
        return 9999.0
    if hours <= 3:
        return 0.5
    if hours <= 24:
        return 2.0
    if hours <= 72:
        return 6.0
    if hours <= 24 * 7:
        return 12.0
    return 24.0


def is_refresh_due(
    *,
    last_generated_at: str | None,
    kickoff_utc: datetime | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    if not last_generated_at:
        return True, "never_generated"
    last = _parse_dt(last_generated_at)
    if last is None:
        return True, "invalid_timestamp"
    now = now or _utc_now()
    interval_h = refresh_interval_hours(kickoff_utc, now=now)
    due_at = last + timedelta(hours=interval_h)
    if now >= due_at:
        return True, f"ttl_expired_{interval_h}h"
    return False, "fresh_ttl"


def immediate_refresh_triggers(
    payload: dict[str, Any] | None,
    *,
    kickoff_utc: datetime | None,
    fixture_hints: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if not payload:
        return True, "missing_payload"
    hints = fixture_hints or {}
    if hints.get("force_refresh_reason"):
        return True, str(hints["force_refresh_reason"])
    signals = payload.get("_prefetch_signals") or payload.get("_predops_signals") or {}
    if signals.get("engine_version") and signals.get("engine_version") != PREDICTION_ENGINE_VERSION:
        return True, "engine_version_changed"
    if hints.get("lineups_official"):
        if not signals.get("lineups_available"):
            return True, "official_lineups"
    if hints.get("major_odds_move"):
        return True, "major_odds_movement"
    if hints.get("injury_update"):
        return True, "injury_update"
    if hints.get("weather_change"):
        return True, "weather_change"
    hours = hours_until_kickoff(kickoff_utc)
    if hours is not None and hours < 0:
        return False, "fixture_finished"
    return False, "no_immediate_trigger"


def should_enqueue_refresh(
    *,
    has_snapshot: bool,
    payload: dict[str, Any] | None,
    last_generated_at: str | None,
    kickoff_utc: datetime | None,
    fixture_hints: dict[str, Any] | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    if force:
        return True, "force"
    hours = hours_until_kickoff(kickoff_utc)
    if hours is not None and hours < 0:
        return False, "finished_fixture"
    if not has_snapshot:
        return True, "missing_snapshot"
    immediate, reason = immediate_refresh_triggers(payload, kickoff_utc=kickoff_utc, fixture_hints=fixture_hints)
    if immediate:
        return True, reason
    due, ttl_reason = is_refresh_due(last_generated_at=last_generated_at, kickoff_utc=kickoff_utc)
    if due:
        return True, ttl_reason
    return False, "fresh_skip"
