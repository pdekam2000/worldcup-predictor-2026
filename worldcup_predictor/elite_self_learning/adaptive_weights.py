"""Part D — adaptive weighting design with drift safeguards."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.elite_self_learning.models import AdaptiveWeightRecommendation, ComponentScore

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "first_goal_team": {
        "first_goal_team_v2": 0.45,
        "egie_historical_baseline": 0.30,
        "goalscorer_intelligence": 0.15,
        "odds_intelligence": 0.10,
        "market_behavior_intelligence": 0.05,
        "lineup_intelligence": 0.05,
        "hybrid_confidence_engine": 0.0,
    },
    "team_to_score_first": {
        "first_goal_team_v2": 0.45,
        "egie_historical_baseline": 0.30,
        "goalscorer_intelligence": 0.15,
        "odds_intelligence": 0.10,
        "market_behavior_intelligence": 0.05,
        "lineup_intelligence": 0.05,
        "hybrid_confidence_engine": 0.0,
    },
    "anytime_goalscorer": {
        "goalscorer_intelligence": 0.55,
        "player_form_store": 0.20,
        "lineup_intelligence": 0.15,
        "odds_intelligence": 0.10,
        "hybrid_confidence_engine": 0.0,
    },
    "1x2": {
        "odds_intelligence": 0.55,
        "market_behavior_intelligence": 0.15,
        "egie_historical_baseline": 0.15,
        "hybrid_confidence_engine": 0.15,
    },
}

ADAPTIVE_CONFIG: dict[str, Any] = {
    "learning_rate": 0.02,
    "max_delta_per_cycle": 0.05,
    "min_weight": 0.02,
    "max_weight": 0.60,
    "min_samples_window": 100,
    "hold_band": 0.02,
    "shadow_only": True,
    "production_write": False,
}


def adaptive_weight_spec() -> dict[str, Any]:
    return {
        "version": "elite_adaptive_weights_v1",
        "defaults": DEFAULT_WEIGHTS,
        "config": ADAPTIVE_CONFIG,
        "evolution_rules": [
            "If help_rate - hurt_rate > 0.08 over window>=100 → increase weight by learning_rate",
            "If hurt_rate - help_rate > 0.08 over window>=100 → decrease weight by learning_rate",
            "Within hold_band → no change",
            "Renormalize market weights to sum=1 after each cycle",
            "Never modify production PredictPipeline weights — shadow JSON only",
        ],
        "safeguards": [
            {
                "id": "shadow_only_gate",
                "description": "Adaptive outputs write to elite_learning_store recommendations — never WDE",
            },
            {
                "id": "max_delta_cap",
                "description": "Single cycle weight change capped at 5%",
            },
            {
                "id": "min_sample_floor",
                "description": "No adaptation until 100 evaluations per component/market",
            },
            {
                "id": "weight_bounds",
                "description": "Components clamped [2%, 60%] to prevent single-source dominance",
            },
            {
                "id": "tier_calibration_check",
                "description": "If Tier A hit rate < Tier B for 200 samples → freeze confidence tiers",
            },
            {
                "id": "league_isolation",
                "description": "UEFA weight changes cannot propagate to WC without 100 league samples",
            },
            {
                "id": "human_approval_gate",
                "description": "Weight shift >10% cumulative requires manual review flag",
            },
            {
                "id": "no_model_retrain",
                "description": "Self-learning adjusts fusion weights only — no automatic model updates",
            },
        ],
    }


def recommend_weights(
    scores: list[ComponentScore],
    *,
    current: dict[str, dict[str, float]] | None = None,
) -> list[AdaptiveWeightRecommendation]:
    """Generate shadow weight recommendations from rolling scores."""
    current = current or DEFAULT_WEIGHTS
    lr = float(ADAPTIVE_CONFIG["learning_rate"])
    max_delta = float(ADAPTIVE_CONFIG["max_delta_per_cycle"])
    min_w = float(ADAPTIVE_CONFIG["min_weight"])
    max_w = float(ADAPTIVE_CONFIG["max_weight"])
    min_n = int(ADAPTIVE_CONFIG["min_samples_window"])
    hold = float(ADAPTIVE_CONFIG["hold_band"])

    # Use window=100 global rollup (league_id None)
    by_key: dict[tuple[str, str], ComponentScore] = {}
    for s in scores:
        if s.window == 100 and s.league_id is None:
            by_key[(s.component_id, s.market_id)] = s

    recs: list[AdaptiveWeightRecommendation] = []
    for market_id, weights in current.items():
        for cid, w in weights.items():
            score = by_key.get((cid, market_id))
            if not score or score.n < min_n:
                recs.append(
                    AdaptiveWeightRecommendation(
                        component_id=cid,
                        market_id=market_id,
                        current_weight=w,
                        recommended_weight=w,
                        delta=0.0,
                        direction="hold",
                        reason=f"insufficient samples (n={score.n if score else 0})",
                    )
                )
                continue
            edge = score.help_rate - score.hurt_rate
            if abs(edge) <= hold:
                direction = "hold"
                delta = 0.0
                reason = f"within hold band (edge={edge:+.3f})"
            elif edge > 0:
                direction = "increase"
                delta = min(max_delta, lr * edge)
                reason = f"outperforming help_rate={score.help_rate:.3f}"
            else:
                direction = "decrease"
                delta = -min(max_delta, lr * abs(edge))
                reason = f"underperforming hurt_rate={score.hurt_rate:.3f}"

            new_w = max(min_w, min(max_w, round(w + delta, 4)))
            recs.append(
                AdaptiveWeightRecommendation(
                    component_id=cid,
                    market_id=market_id,
                    current_weight=w,
                    recommended_weight=new_w,
                    delta=round(new_w - w, 4),
                    direction=direction,
                    reason=reason,
                )
            )
    return recs
