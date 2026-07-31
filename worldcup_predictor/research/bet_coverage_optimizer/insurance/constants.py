"""Insurance Pick constants — research-only, owner-only."""

from __future__ import annotations

PHASE_NAME = "BET_COVERAGE_OPTIMIZER_PHASE3_INSURANCE_AND_REAL_ODDS_VALIDATION"
STATUS_VALIDATED = "BET_COVERAGE_OPTIMIZER_PHASE3_INSURANCE_VALIDATED"
RESEARCH_ONLY = True
OWNER_ONLY = True
PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False

DEFAULT_INSURANCE = {
    "enabled": True,
    "min_odds": 1.55,
    "max_odds": 25.0,
    "min_incremental_uncovered_mass": 0.03,
    "max_primary_overlap_ratio": 0.85,
    "top_k_candidates": 5,
    "max_insurance_tickets": 15,
    "min_insurance_tickets": 3,
    "allow_triple_insurance": False,
    "min_two_leg_joint_mass": 0.02,
    "research_freshness_max_age_hours": 24.0,
}

DEFAULT_INSURANCE_WEIGHTS = {
    "incremental_uncovered_probability_mass": 0.40,
    "residual_risk_reduction": 0.20,
    "estimated_edge": 0.15,
    "log_odds": 0.10,
    "diversification": 0.10,
    "primary_overlap_penalty": 0.05,
}

DEFAULT_BUDGET = {
    "total_budget_eur": 400.0,
    "main_budget_ratio": 0.80,
    "insurance_budget_ratio": 0.20,
    "min_stake_per_ticket_eur": 1.0,
    "max_stake_per_ticket_eur": 20.0,
    "rounding_step_eur": 0.50,
    "stake_mode": "equal",  # equal | score_weighted | kelly_research
    "kelly_enabled": False,
}

SOURCE_TYPES = frozenset(
    {
        "manual_screenshot_transcription",
        "provider_api",
        "research_synthetic",
        "csv_import",
    }
)
