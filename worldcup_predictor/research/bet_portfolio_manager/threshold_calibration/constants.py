"""Threshold calibration package — research-only, baseline policy immutable."""

from __future__ import annotations

PHASE_NAME = "BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_AUDIT"
STATUS_COMPLETE = "BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_COMPLETE"
STATUS_HOLD = "BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_HOLD"
STATUS_RESEARCH_MORE = "BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_RESEARCH_MORE"

BASELINE_COMMIT = "7e77aa3"
BASELINE_POLICY_ID = "baseline_v1_7e77aa3"

ACTIONS = ("BET", "SMALL_BET", "WATCH_NO_CAPITAL", "HARD_SKIP")

# Immutable snapshot of baseline thresholds (do not mutate runtime constants)
BASELINE_POLICY = {
    "policy_version": BASELINE_POLICY_ID,
    "grade_thresholds": {"S": 92.0, "A": 84.0, "B": 72.0, "C": 60.0, "D": 45.0, "F": 0.0},
    "action_thresholds": {"BET": 84.0, "SMALL_BET": 72.0, "WATCH": 55.0, "SKIP": 0.0},
    "gates": {
        "low_entropy_min": 35.0,
        "mean_confidence_min": 35.0,
        "insurance_contribution_min": 15.0,
        "coverage_mass_min_when_weak_ins": 55.0,
        "league_reliability_min": 35.0,
        "min_fixture_score_to_bet": 55.0,
        "correlation_over_concentrated": True,
        "max_day_exposure_frac": 0.60,
        "max_fixture_exposure_frac": 0.35,
    },
    "capital_mode": "score_weighted",
    "watch_micro_allocation_ratio": 0.0,
}
