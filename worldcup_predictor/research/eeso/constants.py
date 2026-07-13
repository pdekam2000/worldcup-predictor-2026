"""EESO shadow research constants — formal namespace over Last-8 components."""

from __future__ import annotations

from worldcup_predictor.research.last8_team_form.constants import (
    COVERAGE_FULL,
    COVERAGE_INSUFFICIENT,
    COVERAGE_LIMITED_3_4,
    COVERAGE_MAPPING_BLOCKED,
    COVERAGE_PARTIAL_5_7,
    COVERAGE_RESULT_MISSING,
    DEFAULT_RECENCY_WEIGHTS,
    MATCHES_REQUESTED,
    PUBLIC_PUBLISH,
    SHADOW_LABEL,
)

PHASE = "EESO-SHADOW-RESEARCH-1"
SHADOW_ONLY = True
PUBLIC_PUBLISH = PUBLIC_PUBLISH

# Promotion gates (shadow research — not automatic production approval).
PROMOTION_MIN_PAIRED_FIXTURES = 1000
PROMOTION_MIN_LEAGUE_FIXTURES = 30
PROMOTION_TOP5_LIFT_PP = 3.0
PROMOTION_TOP3_MAX_DEGRADATION_PP = 1.0
PROMOTION_END_RESULT_MAX_DEGRADATION_PP = 0.5

# Canonical EESO selector keys (shadow selection only; probabilities unchanged).
SELECTOR_CANONICAL_TOP1 = "canonical_top1"
SELECTOR_CANONICAL_TOP3 = "canonical_top3"
SELECTOR_CANONICAL_TOP5 = "canonical_top5"
SELECTOR_PROBABILITY_ONLY = "probability_only"
SELECTOR_WDE_ALIGNED = "wde_aligned_top5"
SELECTOR_LAST8_AWARE = "last8_aware_top5"
SELECTOR_SCENARIO_DIVERSIFIED = "scenario_diversified_top5"
SELECTOR_HYBRID = "hybrid_top5"

METHOD_KEYS_TOP5 = (
    SELECTOR_CANONICAL_TOP5,
    "baseline_top5",
    SELECTOR_WDE_ALIGNED,
    SELECTOR_SCENARIO_DIVERSIFIED,
    SELECTOR_LAST8_AWARE,
    SELECTOR_HYBRID,
)

METHOD_KEYS_TOP3 = (
    "canonical_top3",
    "raw_ecse_top3",
    "wde_aligned_top3",
    "last8_aware_top3",
    "hybrid_coverage_top3",
)

FINAL_STATUS_VALUES = frozenset(
    {
        "EESO_SHADOW_IMPROVES_TOP5",
        "EESO_NO_PROVEN_ADVANTAGE",
        "EESO_MORE_DATA_REQUIRED",
        "EESO_VALIDATION_FAILED",
    }
)

# Named league buckets for breakdown reporting.
NAMED_LEAGUE_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {
    "world_cup": ("World Cup", ("world cup", "world_cup", "fifa world")),
    "uefa": (
        "UEFA competitions",
        ("champions league", "europa league", "conference league", "ucl", "uel", "uefa"),
    ),
    "allsvenskan": ("Allsvenskan", ("allsvenskan",)),
    "eliteserien": ("Eliteserien", ("eliteserien",)),
    "urvalsdeild": ("Urvalsdeild", ("urvalsdeild", "úrvalsdeild")),
    "one_deild": ("1. deild Iceland", ("one_deild", "1. deild", "1 deild")),
    "veikkausliiga": ("Veikkausliiga", ("veikkausliiga",)),
    "superettan": ("Superettan", ("superettan",)),
    "virsliga": ("Virsliga", ("virsliga", "virslīga")),
    "a_lyga": ("A Lyga", ("a lyga", "a_lyga", "alyga")),
}

COVERAGE_FLAG_ALIASES: dict[str, str] = {
    "ALL_TOP5_SAME_CLEAN_SHEET_SCENARIO": "ALL_TOP5_CLEAN_SHEET",
    "NO_HIGH_SCORE_TAIL_COVERAGE": "NO_HIGH_SCORE_TAIL",
}

REQUIRED_COVERAGE_WARNINGS = frozenset(
    {
        "ALL_TOP5_CLEAN_SHEET",
        "ALL_TOP5_BTTS_NO",
        "NO_DRAW_COVERAGE",
        "NO_OPPONENT_ONE_GOAL_COVERAGE",
        "NO_HIGH_SCORE_TAIL",
        "TOP5_OVER_CONCENTRATED",
        "TOP5_UNDER_DIVERSIFIED",
    }
)

ARTIFACT_SUBDIR = "eeso_shadow"
