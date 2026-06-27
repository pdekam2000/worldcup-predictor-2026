"""Smart refresh signals — orchestration only (no engine changes)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from worldcup_predictor.automation.worldcup_background.freshness import hours_until_kickoff, _parse_dt
from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
    is_stored_prediction_quality_valid,
)
from worldcup_predictor.prediction.engine_versions import PREDICTION_ENGINE_VERSION


def _fingerprint(obj: Any) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        raw = str(obj)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_prefetch_signals(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp on stored payload after generation (orchestration metadata)."""
    odds = payload.get("odds") or payload.get("betting_intelligence") or {}
    weather = payload.get("weather_intelligence") or payload.get("weather") or {}
    lineups = payload.get("expected_lineups") or payload.get("lineup_intelligence") or {}
    return {
        "engine_version": payload.get("prediction_engine_version") or PREDICTION_ENGINE_VERSION,
        "lineups_available": bool(lineups.get("available") or lineups.get("home_xi")),
        "odds_fp": _fingerprint(odds) if odds else None,
        "weather_fp": _fingerprint(weather) if weather else None,
        "no_bet": bool(payload.get("no_bet")),
        "has_best_pick": bool(
            payload.get("best_available_pick")
            or payload.get("value_pick")
            or payload.get("safe_pick")
        ),
    }


def should_refresh_for_signals(
    payload: dict[str, Any] | None,
    *,
    kickoff_utc,
    fixture_hints: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Detect orchestration-level refresh triggers beyond TTL freshness.
    Does not call providers — uses payload fingerprints and kickoff proximity.
    """
    if not payload or payload.get("status") != "ok":
        return True, "missing_or_invalid_payload"

    quality_ok, qreason = is_stored_prediction_quality_valid(payload)
    if not quality_ok:
        return True, qreason

    hours = hours_until_kickoff(_parse_dt(kickoff_utc) or _parse_dt(payload.get("kickoff_utc")))
    signals = payload.get("_prefetch_signals") or {}
    hints = fixture_hints or {}

    # Lineup window: refresh once inside 6h if prior run had no lineups signal
    if hours is not None and 0 < hours <= 6:
        if not signals.get("lineups_available") and hints.get("lineups_expected"):
            return True, "lineup_window_refresh"

    # Engine version drift
    if signals.get("engine_version") and signals.get("engine_version") != PREDICTION_ENGINE_VERSION:
        return True, "engine_version_changed"

    # Hint flags from schedule row (optional)
    if hints.get("force_refresh_reason"):
        return True, str(hints["force_refresh_reason"])

    return False, "signals_ok"
