"""Part C — unified confidence fusion model."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.elite_orchestrator.models import ConfidenceTier, FusionSignal


def confidence_fusion_spec() -> dict[str, Any]:
    """Design spec for Tier A–D fusion across validated components."""
    return {
        "version": "elite_confidence_fusion_v1",
        "tier_thresholds": {
            "A": 0.72,
            "B": 0.58,
            "C": 0.42,
            "D": 0.0,
        },
        "signals": {
            FusionSignal.MODEL_AGREEMENT.value: {
                "description": "Agreement between EGIE baseline, FGT V2, and goalscorer team proxy",
                "weight": 0.30,
                "formula": "1 - normalized_disagreement(component_predictions)",
                "markets": ["first_goal_team", "team_to_score_first", "anytime_goalscorer"],
            },
            FusionSignal.MARKET_AGREEMENT.value: {
                "description": "Model pick aligns with implied odds favorite / goalscorer odds rank",
                "weight": 0.20,
                "formula": "binary(model_pick == odds_favorite) * odds_margin",
                "markets": ["1x2", "anytime_goalscorer", "first_goal_team"],
            },
            FusionSignal.MBI_PRIOR.value: {
                "description": "MBI bucket prior supports model direction (10% blend feasible)",
                "weight": 0.10,
                "formula": "clamp(1 - abs(model_prob - bucket_hit_rate), 0, 1)",
                "markets": ["1x2", "first_goal_team"],
                "max_blend_weight": 0.10,
            },
            FusionSignal.ODDS_CONFIDENCE.value: {
                "description": "Sharp consensus, movement stability, market depth",
                "weight": 0.25,
                "formula": "0.5*consensus_strength + 0.3*movement_stability + 0.2*book_count_norm",
                "markets": ["1x2", "first_goal_team", "team_to_score_first"],
            },
            FusionSignal.DATA_QUALITY.value: {
                "description": "Lineup confirmed, player history depth, odds coverage",
                "weight": 0.15,
                "formula": "0.4*lineup_dq + 0.35*player_history + 0.25*odds_coverage",
                "markets": "all",
            },
        },
        "market_overrides": {
            "anytime_goalscorer": {
                "primary_signal": FusionSignal.MODEL_AGREEMENT.value,
                "secondary_signal": FusionSignal.DATA_QUALITY.value,
                "odds_weight_cap": 0.15,
                "notes": "UEFA odds sparse — cap odds influence",
            },
            "first_goalscorer": {
                "primary_signal": FusionSignal.DATA_QUALITY.value,
                "tier_cap": "B",
                "notes": "31% top-3 — never Tier A without odds alignment",
            },
            "goal_timing": {
                "inherit": "hybrid_confidence_engine",
                "notes": "Reuse 52D conf_range / conf_minute; minute stays experimental",
            },
        },
        "tier_rules": [
            "Tier A requires MODEL_AGREEMENT >= 0.75 AND DATA_QUALITY >= 0.70",
            "Tier A for goalscorer requires WC odds OR top-1 margin >= 2x over rank-2",
            "Tier D if any critical input missing (no lineup AND no odds for team markets)",
            "MBI prior alone cannot elevate tier — only modulates probability",
        ],
        "fusion_formula": "conf = clamp(sum(signal_weight * signal_score) * tier_multiplier)",
    }


def compute_tier(confidence: float, thresholds: dict[str, float] | None = None) -> ConfidenceTier:
    t = thresholds or {"A": 0.72, "B": 0.58, "C": 0.42, "D": 0.0}
    if confidence >= t["A"]:
        return "A"
    if confidence >= t["B"]:
        return "B"
    if confidence >= t["C"]:
        return "C"
    return "D"


def model_agreement_score(predictions: dict[str, Any]) -> float:
    """Normalized agreement across component predictions (design helper)."""
    picks = [p for p in predictions.values() if p is not None]
    if len(picks) < 2:
        return 0.5
    mode_count = max(picks.count(x) for x in set(picks))
    return round(mode_count / len(picks), 4)
