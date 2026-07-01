"""PHASE ECSE-X3-A — Composite market algebra shadow constants."""

from __future__ import annotations

PHASE = "ECSE-X3-A"
METHOD_VERSION = "ECSE-X3-A-v1"

SHADOW_ARTIFACT = "artifacts/ecse_x3_a_composite_shadow.jsonl"
SUMMARY_ARTIFACT = "artifacts/ecse_x3_a_composite_shadow_summary.json"

TOP_N_SHADOW = 10
TOP_N_STORE = 15

TRAIN_FRACTION = 0.70
NUM_TEMPORAL_FOLDS = 5

ZZ2_BTTS_MIN = 0.56
ZZ2_U25_MIN = 0.52

MIN_HOME_PROB = 0.55
STRONG_HOME_PROB = 0.60
DRAW_HIGH_MIN = 0.30
BTTS_HIGH_MIN = 0.56
UNDER_HIGH_MIN = 0.52
OVER_HIGH_MIN = 0.52

# Boost strengths (research-only, inside Top-10 pool)
H_BOOST = 1.18
I_BOOST = 1.16
ZZ2_BOOST = 1.28
J2_G_SLOPE_STRENGTH = 0.12
SEGMENT_H_MULT = 1.25
SEGMENT_I_MULT = 1.25

CONSERVATIVE_MIN_FAMILIES = 4

MAX_TOP3_WORSEN = 0.75
MAX_LOG_LOSS_WORSEN = 0.01
MIN_FOLDS_IMPROVED = 3
MIN_ELIGIBLE_SAMPLE = 3_000

PROMOTE_TOP1_MIN = 0.75
PROMOTE_TOP3_MIN = 0.75
PROMOTE_TOP5_MIN = 1.00

METHODS = (
    "champion",
    "hi_only",
    "zz2_only",
    "j2_g_slope",
    "composite_full",
    "conservative_composite",
    "segment_aware",
)

HOME_WIN_SCORELINES = frozenset({"1-0", "2-0", "2-1", "3-1", "3-0", "4-1"})
DRAW_UNDER_SCORELINES = frozenset({"0-0", "1-1", "0-1", "1-2"})
ZZ2_TARGET = "1-1"

RECOMMENDATIONS = (
    "PROMOTE_COMPOSITE_TO_OWNER_LAB",
    "KEEP_SHADOW_MORE_DATA",
    "USE_ONLY_ZZ2_DETECTOR",
    "USE_ONLY_HI_J2_G_SLOPE",
    "NEED_MORE_ODDS_COVERAGE",
    "REJECT_COMPOSITE",
)

ACCEPTED_SIGNALS = (
    "H = (ph + p_o25 + p_btts) / 3",
    "I = (pd + p_u25 + p_btts_no) / 3",
    "ZZ2 = p_btts > 0.56 AND p_u25 > 0.52",
    "J2 = p_o25 / p_btts",
    "G = abs(ph - pa) / p_o25",
    "OU_slope = p_o15 / p_o25",
)

REJECTED_SIGNALS = (
    "Equation A raw odds",
    "Fibonacci / phi / 1.618",
    "Equation D redundant with p_ht_o15",
    "Mystical / non-probabilistic patterns",
)
