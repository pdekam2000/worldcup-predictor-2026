"""TSBP-1 — Team Strength Bivariate Poisson (Challenger shadow only)."""

from __future__ import annotations

from typing import Final

TSBP_MODEL_ID: Final = "TSBP-1"
TSBP_MODEL_NAME: Final = "Team Strength Bivariate Poisson"
TSBP_MODEL_FAMILY: Final = "bivariate_poisson"
TSBP_MODEL_VERSION: Final = "1.0.0"
TSBP_DISTRIBUTION: Final = "BIVARIATE_POISSON"
TSBP_STATUS: Final = "FORWARD_SHADOW"
TSBP_LABEL: Final = "TSBP_SHADOW"

TSBP_IS_SHADOW: Final = True
TSBP_PUBLIC_VISIBLE: Final = False
TSBP_FINAL_DECISION_AUTHORITY: Final = False

GBGM1_MODEL_ID: Final = "GBGM-1"
GBGM1_STATUS: Final = "PAUSED_BELOW_BASELINE"

DOMAIN_POLICY_VERSION: Final = "tsbp-domain-v1"

DOMAIN_FORWARD_ENABLED = "TSBP_FORWARD_ENABLED"
DOMAIN_RESEARCH_ONLY = "TSBP_RESEARCH_ONLY"
DOMAIN_DATA_BLOCKED = "TSBP_DATA_BLOCKED"
DOMAIN_UNSUPPORTED = "TSBP_UNSUPPORTED"

# Phase 3B evidence: PL + BL beat league baseline with team strength.
DEFAULT_FORWARD_ENABLED: tuple[str, ...] = (
    "premier_league",
    "bundesliga",
)
DEFAULT_RESEARCH_ONLY: tuple[str, ...] = (
    "champions_league",
    "world_cup_2026",
)

MIN_LEAGUE_HISTORY = 80
MIN_TEAM_GAMES = 3
MAX_GOALS_GRID = 7
BIVARIATE_CORR = 0.05
HOME_ADVANTAGE_FROM_LEAGUE = True  # encoded in league home/away means

FORWARD_THRESHOLDS_TSBP = {
    25: "operational_check_only",
    50: "initial_diagnostic",
    100: "preliminary_statistical_review",
    250: "promotion_quality_review",
    500: "stronger_multi_domain_evidence",
}

SNAPSHOT_PARITY_FAILED = "SNAPSHOT_PARITY_FAILED"
