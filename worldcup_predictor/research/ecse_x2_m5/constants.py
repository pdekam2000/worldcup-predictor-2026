"""PHASE ECSE-X2-M5 — Shortlist enhancer constants."""

from __future__ import annotations

PHASE = "ECSE-X2-M5"
METHOD_VERSION = "ECSE-X2-M5-v1"
EQUATION_NAME = "log_home_prob_phi"

SHADOW_ARTIFACT = "artifacts/ecse_x2_m5_shortlist_enhancer.jsonl"
SUMMARY_ARTIFACT = "artifacts/ecse_x2_m5_shortlist_enhancer_summary.json"

M4_WEIGHT = 0.05
TIE_BREAK_EPSILON = 0.008
TIE_BREAK_MIN_HOME_PROB = 0.60
SHORTLIST_TOP_N = 10
TOP_N_STORE = 15

TRAIN_FRACTION = 0.70
NUM_TEMPORAL_FOLDS = 5

MAX_TOP3_WORSEN = 0.15
MAX_LOG_LOSS_WORSEN = 0.01
MAX_RANK_VOLATILITY = 2.0
MIN_FOLDS_IMPROVED_TOP5 = 3
MIN_ELIGIBLE_SAMPLE = 3_000

MIN_HOME_PROB = 0.55
STRONG_HOME_PROB = 0.60

METHODS = (
    "champion",
    "m3_full_reorder",
    "m4_weight_005",
    "shortlist_enhancer",
    "tie_breaker",
)

SEGMENTS = (
    "all_eligible",
    "home_ge_55",
    "home_ge_60",
    "home_favorite",
    "strong_home_favorite",
    "balanced_control",
)

RECOMMENDATIONS = (
    "PROMOTE_SHORTLIST_SHADOW_LIVE",
    "USE_AS_ADMIN_ONLY_SIGNAL",
    "KEEP_RESEARCH_ONLY",
    "REJECT_NO_SHORTLIST_VALUE",
    "NEED_MORE_ODDS_COVERAGE",
)
