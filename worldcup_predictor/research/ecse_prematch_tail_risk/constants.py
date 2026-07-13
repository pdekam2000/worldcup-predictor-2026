"""ECSE prematch tail-risk detector — shadow research constants."""

from __future__ import annotations

PHASE = "ECSE-PREMATCH-TAIL-RISK-DETECTOR-1"
SHADOW_ONLY = True
PUBLIC_PUBLISH = False
ARTIFACT_SUBDIR = "ecse_prematch_tail_risk"

TRAIN_END_DATE = "2024-01-01"
VALIDATE_START_DATE = "2024-01-01"

TIER_LOW = "LOW"
TIER_MEDIUM = "MEDIUM"
TIER_HIGH = "HIGH"
TIER_VERY_HIGH = "VERY_HIGH"

TAIL_RISK_TIERS = (TIER_LOW, TIER_MEDIUM, TIER_HIGH, TIER_VERY_HIGH)

# Promotion gate (segment router research — not production).
GATE_MIN_OOT_FIXTURES = 10_000
GATE_MIN_DETECTOR_POSITIVE = 500
GATE_CONDITIONAL_TOP5_LIFT_PP = 2.0
GATE_GLOBAL_TOP5_MAX_DEGRADATION_PP = 0.2
GATE_TOP3_MAX_DEGRADATION_PP = 0.5
GATE_PRECISION_ABOVE_BASE_MULT = 1.5

FINAL_STATUS_VALUES = frozenset(
    {
        "PREMATCH_TAIL_DETECTOR_SEGMENT_LIFT_VALIDATED",
        "PREMATCH_TAIL_DETECTOR_FOUND_NO_ACTIONABLE_EDGE",
        "PREMATCH_TAIL_DETECTOR_MORE_DATA_REQUIRED",
        "PREMATCH_TAIL_DETECTOR_VALIDATION_FAILED",
    }
)

FEATURE_COLUMNS = (
    "lambda_home",
    "lambda_away",
    "total_lambda",
    "lambda_gap",
    "entropy",
    "top3_mass",
    "top5_mass",
    "canonical_high_score_tail_mass",
    "canonical_btts_mass",
    "prob_home_scores_3plus",
    "prob_away_scores_2plus",
    "prob_both_teams_score",
    "prob_favourite_concedes_one",
    "prob_favourite_concedes_two_plus",
    "implied_over_25",
    "implied_btts_yes",
    "odds_home",
    "odds_draw",
    "odds_away",
    "favourite_odds",
    "wde_home_prob",
    "wde_draw_prob",
    "wde_away_prob",
    "last8_home_avg_scored",
    "last8_home_avg_conceded",
    "last8_away_avg_scored",
    "last8_away_avg_conceded",
    "last8_home_scored_in_rate",
    "last8_away_scored_in_rate",
    "last8_home_btts_rate",
    "last8_away_btts_rate",
    "last8_home_over25_rate",
    "last8_away_over25_rate",
    "league_avg_goals",
    "league_btts_rate",
    "league_high_tail_rate",
)
