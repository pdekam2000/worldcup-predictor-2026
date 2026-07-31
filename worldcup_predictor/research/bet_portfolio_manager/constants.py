"""Bet Portfolio Manager constants — research-only."""

from __future__ import annotations

PHASE_NAME = "BET_PORTFOLIO_MANAGER_RESEARCH"
STATUS_COMPLETE = "BET_PORTFOLIO_MANAGER_RESEARCH_COMPLETE"
RESEARCH_ONLY = True
OWNER_ONLY = True
NO_PRODUCTION_DEPLOY = True
PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False

# Grades by daily portfolio score
GRADE_THRESHOLDS = (
    (92.0, "S"),
    (84.0, "A"),
    (72.0, "B"),
    (60.0, "C"),
    (45.0, "D"),
    (0.0, "F"),
)

# Day-level action thresholds
ACTION_THRESHOLDS = (
    (84.0, "BET"),
    (72.0, "SMALL BET"),
    (55.0, "WATCH"),
    (0.0, "SKIP"),
)

DEFAULT_BANKROLLS = (100.0, 250.0, 500.0, 1000.0)
MAX_FIXTURE_EXPOSURE_FRAC = 0.35
MAX_DAY_EXPOSURE_FRAC = 0.60
MIN_FIXTURE_SCORE_TO_BET = 55.0
KELLY_FRACTION = 0.25  # research fractional Kelly only

SCORE_WEIGHTS = {
    "mean_confidence": 0.18,
    "low_entropy": 0.14,
    "coverage_mass": 0.14,
    "low_residual_risk": 0.12,
    "insurance_contribution": 0.10,
    "odds_balance": 0.08,
    "market_diversity": 0.06,
    "fixture_count_quality": 0.06,
    "league_reliability": 0.08,
    "low_correlation": 0.04,
}
