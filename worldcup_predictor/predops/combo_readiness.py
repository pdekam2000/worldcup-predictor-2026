"""PredOps combo readiness — Phase A15 + A16 market-quality gates."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.api.match_center_helpers import extract_prediction_summary
from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt, is_prediction_fresh
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.predops.store import PredOpsStore
from worldcup_predictor.publication.bet_quality_overlay import build_publication_overlay

COMBO_QUALITY_THRESHOLDS: dict[str, float] = {
    "safe": 90.0,
    "balanced": 75.0,
    "value": 60.0,
    "high_odds": 45.0,
}

DEFAULT_MIN_QUALITY = 45.0


def _leg_eligible(
    summary: dict[str, Any],
    payload: dict[str, Any],
    overlay: dict[str, Any],
    *,
    min_quality: float,
) -> tuple[bool, str]:
    if not summary or not payload:
        return False, "missing_summary"
    status = overlay.get("public_recommendation_status")
    if status == "unavailable":
        return False, "unavailable"
    bqs = float(overlay.get("bet_quality_score") or 0)
    if bqs < min_quality:
        return False, "low_quality"
    if not summary.get("best_pick") and not overlay.get("public_best_pick"):
        return False, "no_pick"
    kick = _parse_dt(payload.get("kickoff_utc"))
    fresh, _ = is_prediction_fresh(payload, kickoff_utc=kick)
    if not fresh:
        return False, "stale"
    return True, "ready"


def build_combo_readiness_report(
    *,
    settings: Settings | None = None,
    matches: list[dict[str, Any]] | None = None,
    min_confidence: float = DEFAULT_MIN_QUALITY,
) -> dict[str, Any]:
    """Evaluate combo leg eligibility from latest predops snapshots (market quality)."""
    settings = settings or get_settings()
    store = PredOpsStore(settings)
    min_quality = max(min_confidence, DEFAULT_MIN_QUALITY)

    if matches is None:
        from worldcup_predictor.automation.prediction_prefetch.coverage import collect_upcoming_fixtures

        fixtures = collect_upcoming_fixtures(settings=settings, window_days=7)
        matches = [
            {
                "fixture_id": f["fixture_id"],
                "competition_key": f["competition_key"],
                "kickoff_utc": f.get("kickoff_utc"),
            }
            for f in fixtures
        ]

    fixture_ids = [int(m["fixture_id"]) for m in matches if m.get("fixture_id")]
    snaps = store.latest_by_fixtures(fixture_ids)

    eligible_by_mode: dict[str, list[dict[str, Any]]] = {k: [] for k in COMBO_QUALITY_THRESHOLDS}
    reasons: dict[str, int] = {}
    caution_count = 0

    for m in matches:
        fid = int(m["fixture_id"])
        snap = snaps.get(fid)
        payload = (snap or {}).get("payload") or {}
        summary = extract_prediction_summary(payload)
        overlay = build_publication_overlay(payload, include_debug=False)
        if overlay.get("public_recommendation_status") == "caution_best_available":
            caution_count += 1

        leg_base = {
            "fixture_id": fid,
            "competition_key": m.get("competition_key"),
            "best_pick": summary.get("best_pick") or overlay.get("public_best_pick"),
            "confidence": summary.get("confidence"),
            "bet_quality_score": overlay.get("bet_quality_score"),
            "bet_quality_tier": overlay.get("bet_quality_tier"),
            "public_recommendation_status": overlay.get("public_recommendation_status"),
            "caution": overlay.get("public_recommendation_status") == "caution_best_available",
            "snapshot_id": (snap or {}).get("snapshot_id"),
        }

        any_mode = False
        for mode, threshold in COMBO_QUALITY_THRESHOLDS.items():
            ok, reason = _leg_eligible(summary, payload, overlay, min_quality=threshold)
            if not ok:
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            eligible_by_mode[mode].append({**leg_base, "combo_mode": mode})
            any_mode = True

        if not any_mode:
            ok, reason = _leg_eligible(summary, payload, overlay, min_quality=min_quality)
            if not ok:
                reasons[reason] = reasons.get(reason, 0) + 1

    all_eligible = eligible_by_mode["high_odds"]
    no_combo_reason = None
    if not all_eligible:
        if reasons.get("low_quality", 0) > 0:
            no_combo_reason = "low_quality"
        elif reasons.get("unavailable", 0) > 0:
            no_combo_reason = "unavailable_markets"
        elif reasons.get("missing_summary", 0) > 0:
            no_combo_reason = "no_bettable_predictions"
        elif reasons.get("stale", 0) > 0:
            no_combo_reason = "stale_predictions"
        else:
            no_combo_reason = "insufficient_fixtures"

    return {
        "status": "ok",
        "eligible_legs": len(all_eligible),
        "eligible": all_eligible[:50],
        "eligible_by_mode": {k: v[:30] for k, v in eligible_by_mode.items()},
        "caution_best_available_count": caution_count,
        "reason_counts": reasons,
        "combos": {
            "safe_ready": len(eligible_by_mode["safe"]) >= 2,
            "balanced_ready": len(eligible_by_mode["balanced"]) >= 3,
            "value_ready": len(eligible_by_mode["value"]) >= 3,
            "high_odds_ready": len(eligible_by_mode["high_odds"]) >= 4,
        },
        "no_combo_reason": no_combo_reason,
        "min_quality": min_quality,
        "quality_thresholds": COMBO_QUALITY_THRESHOLDS,
    }
