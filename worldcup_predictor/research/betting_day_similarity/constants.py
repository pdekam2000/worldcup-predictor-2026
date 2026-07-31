"""Constants for Betting Day Similarity Engine research."""

from __future__ import annotations

PHASE_NAME = "BETTING_DAY_SIMILARITY_ENGINE_RESEARCH"
STATUS_COMPLETE = "BETTING_DAY_SIMILARITY_ENGINE_RESEARCH_COMPLETE"
STATUS_HOLD = "BETTING_DAY_SIMILARITY_ENGINE_HOLD"
STATUS_RESEARCH_MORE = "BETTING_DAY_SIMILARITY_ENGINE_RESEARCH_MORE"

BASELINE_COMMIT = "aa2af6a"
BASELINE_PM_POLICY_ID = "baseline_v1_7e77aa3"
CALIBRATED_POLICY_PATH = (
    "worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json"
)

RECOMMENDATIONS = (
    "FAVORABLE_SIMILARITY",
    "MODERATELY_FAVORABLE",
    "NEUTRAL",
    "UNCERTAIN_LOW_SAMPLE",
    "HOSTILE_SIMILARITY",
    "OUT_OF_DISTRIBUTION",
)

OVERLAY_ACTIONS = (
    "SIMILARITY_SUPPORTS",
    "SIMILARITY_NEUTRAL",
    "SIMILARITY_REDUCE",
    "SIMILARITY_SKIP_OOD",
)

OOD_LEVELS = (
    "in_distribution",
    "mildly_out_of_distribution",
    "strongly_out_of_distribution",
)

GRADE_THRESHOLDS = {"S": 90.0, "A": 80.0, "B": 70.0, "C": 55.0, "D": 40.0, "F": 0.0}

# Features that must NEVER appear in live similarity vectors
FORBIDDEN_LIVE_FEATURES = frozenset(
    {
        "realized_roi",
        "net_return",
        "max_daily_loss",
        "coupon_survival_realized",
        "complete_coupon_failure_realized",
        "insurance_rescue_count_realized",
        "hit_insurance",
        "actual_score",
        "exact_score_actual_rank",
        "final_coupon_profit",
        "post_kickoff_odds",
    }
)

DEFAULT_SEED = 20260731
