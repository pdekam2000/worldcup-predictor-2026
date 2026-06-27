"""EGIE snapshot block — Phase A15 (metadata extraction only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.prediction.engine_versions import PREDICTION_ENGINE_VERSION


def build_egie_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    gt = payload.get("goal_timing") or payload.get("egie") or {}
    if not isinstance(gt, dict):
        gt = {}
    dm = payload.get("detailed_markets") or {}
    if isinstance(dm, dict):
        for k in ("goal_timing", "first_goal_team", "goalscorer"):
            if dm.get(k) and k not in gt:
                gt = {**gt, k: dm[k]}

    has_pick = any(
        gt.get(k)
        for k in (
            "first_goal_team",
            "first_goal_time_range",
            "estimated_first_goal_minute",
            "next_goal_team",
        )
    )

    status = "available"
    reason = None
    if not gt:
        status = "missing"
        reason = "egie_block_absent"
    elif gt.get("no_pick") or gt.get("status") == "no_pick":
        status = "no_pick"
        reason = gt.get("reason") or "egie_no_pick"
    elif not has_pick:
        status = "unavailable"
        reason = gt.get("unavailable_reason") or "insufficient_data"

    return {
        "status": status,
        "reason": reason,
        "first_goal_team": gt.get("first_goal_team"),
        "first_goal_time_range": gt.get("first_goal_time_range"),
        "estimated_first_goal_minute": gt.get("estimated_first_goal_minute"),
        "next_goal_team": gt.get("next_goal_team"),
        "team_goals_home": gt.get("team_goals_home"),
        "team_goals_away": gt.get("team_goals_away"),
        "anytime_goalscorer_candidates": gt.get("anytime_goalscorer_candidates") or gt.get("goalscorer_candidates"),
        "first_goalscorer_candidates": gt.get("first_goalscorer_candidates"),
        "player_most_likely_to_score": gt.get("player_most_likely_to_score") or gt.get("most_likely_scorer"),
        "confidence": gt.get("confidence") or gt.get("egie_confidence"),
        "reliability": gt.get("reliability") or gt.get("egie_reliability"),
        "model_version": gt.get("model_version") or gt.get("version"),
        "generated_at": gt.get("generated_at") or payload.get("generated_at"),
        "data_sources_used": gt.get("data_sources_used") or [],
        "missing_requirements": gt.get("missing_requirements") or gt.get("missing_data") or [],
        "next_refresh_trigger": gt.get("next_refresh_trigger"),
        "engine_version": payload.get("prediction_engine_version") or PREDICTION_ENGINE_VERSION,
    }
