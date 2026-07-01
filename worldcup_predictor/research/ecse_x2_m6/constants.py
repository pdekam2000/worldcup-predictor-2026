"""PHASE ECSE-X2-M6 — Shadow-live integration constants."""

from __future__ import annotations

PHASE = "ECSE-X2-M6"
METHOD_VERSION = "ECSE-X2-M6-v1"
EQUATION_NAME = "log_home_prob_phi"

SHADOW_ARTIFACT = "artifacts/ecse_x2_m6_shadow_live_shortlists.jsonl"
EVAL_ARTIFACT = "artifacts/ecse_x2_m6_shadow_live_evaluations.jsonl"

MIN_HOME_PROB_PREFERRED = 0.55
STRONG_HOME_PROB = 0.60
SHORTLIST_TOP_N = 10

RECOMMENDATIONS = (
    "SHADOW_LIVE_READY",
    "ADMIN_PREVIEW_READY",
    "NEED_ODDS_COVERAGE",
    "NEED_EVALUATION_DATA",
    "DO_NOT_PROMOTE",
)
