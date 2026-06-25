"""Part D — elite shadow prediction object schema and example builder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.elite_orchestrator.confidence import compute_tier
from worldcup_predictor.elite_orchestrator.models import (
    ComponentContribution,
    EliteShadowPrediction,
    MarketShadowOutput,
)


def shadow_output_schema() -> dict[str, Any]:
    """JSON schema description for internal shadow prediction object."""
    return {
        "$schema": "elite_shadow_prediction_v1",
        "required": [
            "fixture_id",
            "competition_key",
            "generated_at",
            "markets",
            "fusion",
        ],
        "market_fields": {
            "prediction": "Market-specific pick or ranked list",
            "confidence": "Fused scalar 0–1",
            "tier": "A | B | C | D",
            "evidence": "Structured facts supporting the pick",
            "reasoning": "Human-readable bullet strings",
            "component_contributions": [
                {
                    "component_id": "str",
                    "weight": "float 0–1",
                    "prediction": "component-level pick",
                    "confidence": "float",
                    "evidence": "dict",
                }
            ],
        },
        "fusion_block": {
            "model_agreement": "float",
            "market_agreement": "float",
            "mbi_prior_applied": "bool",
            "mbi_blend_weight": "float",
            "odds_confidence": "float",
            "data_quality": "float",
            "overall_tier": "A-D",
        },
        "storage": {
            "path": "data/shadow/elite_orchestrator_predictions.jsonl",
            "format": "one JSON object per fixture per run",
        },
    }


def build_example_shadow_prediction(
    *,
    fixture_id: int = 0,
    sportmonks_fixture_id: int | None = None,
    competition_key: str = "design_example",
) -> EliteShadowPrediction:
    """Illustrative shadow object — not a live prediction."""
    fusion = {
        "model_agreement": 0.82,
        "market_agreement": 0.71,
        "mbi_prior_applied": True,
        "mbi_blend_weight": 0.10,
        "odds_confidence": 0.68,
        "data_quality": 0.85,
        "overall_tier": "B",
    }

    fgt_conf = 0.64
    markets = {
        "first_goal_team": MarketShadowOutput(
            market_id="first_goal_team",
            prediction="home",
            confidence=fgt_conf,
            tier=compute_tier(fgt_conf),
            evidence={
                "fgt_v2_prob_home": 0.58,
                "egie_baseline": "home",
                "top_home_goals_per_90": 0.62,
                "fts_implied_home": 0.54,
            },
            reasoning=[
                "Goalscorer intel favors home top scorer (goals_per_90 lead +0.18)",
                "EGIE baseline agrees on home first goal",
                "MBI bucket prior neutral at current FTS odds",
            ],
            component_contributions=[
                ComponentContribution("first_goal_team_v2", 0.45, "home", 0.58, {"group": "baseline_goalscorer"}),
                ComponentContribution("egie_historical_baseline", 0.30, "home", 0.52, {}),
                ComponentContribution("goalscorer_intelligence", 0.15, "home", 0.61, {"intel_gap": 0.18}),
                ComponentContribution("odds_intelligence", 0.10, "home", 0.54, {"fts_implied": 0.54}),
            ],
        ),
        "team_to_score_first": MarketShadowOutput(
            market_id="team_to_score_first",
            prediction="home",
            confidence=fgt_conf,
            tier=compute_tier(fgt_conf),
            evidence={"alias_of": "first_goal_team", "same_fusion_path": True},
            reasoning=["Mirrors first_goal_team fusion — same underlying signal"],
            component_contributions=[],
        ),
        "anytime_goalscorer": MarketShadowOutput(
            market_id="anytime_goalscorer",
            prediction=["Player A", "Player B", "Player C"],
            confidence=0.59,
            tier="B",
            evidence={"top3_composite_hit_rate_ref": 0.571, "lineup_confirmed": True},
            reasoning=[
                "Combined score ranks top-3 from player form + lineup eligibility",
                "No goalscorer odds — odds confidence capped",
            ],
            component_contributions=[
                ComponentContribution("goalscorer_intelligence", 0.70, ["Player A", "Player B", "Player C"], 0.59, {}),
                ComponentContribution("player_form_store", 0.20, None, 0.55, {"form_score": 0.72}),
                ComponentContribution("lineup_intelligence", 0.10, None, 0.80, {"starters": 11}),
            ],
        ),
        "1x2": MarketShadowOutput(
            market_id="1x2",
            prediction={"home": 0.42, "draw": 0.28, "away": 0.30},
            confidence=0.48,
            tier="C",
            evidence={"mbi_prior_shift": 0.02, "odds_books": 8},
            reasoning=["Odds-led with 10% MBI bucket prior on home short-price bucket"],
            component_contributions=[
                ComponentContribution("odds_intelligence", 0.60, {"home": 0.40}, 0.50, {}),
                ComponentContribution("market_behavior_intelligence", 0.10, None, 0.45, {"bucket": "2.40-2.50"}),
            ],
        ),
        "first_goalscorer": MarketShadowOutput(
            market_id="first_goalscorer",
            prediction=["Player A", "Player B", "Player C"],
            confidence=0.38,
            tier="C",
            evidence={"top3_first_goal_ref": 0.31},
            reasoning=["Research tier — first goalscorer accuracy below anytime"],
            component_contributions=[
                ComponentContribution("goalscorer_intelligence", 0.85, ["Player A"], 0.38, {}),
            ],
        ),
        "goal_timing": MarketShadowOutput(
            market_id="goal_timing",
            prediction={"range": "16-30", "minute_estimate": 24},
            confidence=0.35,
            tier="C",
            evidence={"inherits": "hybrid_confidence_engine", "conf_range": 0.41},
            reasoning=["EGIE survival range — minute experimental per 52D"],
            component_contributions=[
                ComponentContribution("egie_historical_baseline", 0.90, {"range": "16-30"}, 0.35, {}),
                ComponentContribution("hybrid_confidence_engine", 0.10, None, 0.41, {}),
            ],
        ),
    }

    return EliteShadowPrediction(
        fixture_id=fixture_id,
        sportmonks_fixture_id=sportmonks_fixture_id,
        competition_key=competition_key,
        generated_at=datetime.now(timezone.utc).isoformat(),
        markets=markets,
        fusion=fusion,
        meta={"mode": "design_example", "production": False},
    )
