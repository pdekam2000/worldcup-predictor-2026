"""PHASE ECSE-X3-B — Owner shadow lab wiring constants."""

from __future__ import annotations

PHASE = "ECSE-X3-B"
METHOD_VERSION = "ECSE-X3-B-v1"
CANDIDATE_ID = "ecse_x3_j2_g_slope"
DISPLAY_LABEL = "ECSE X3 — J2/G/OU Slope"
MODE = "shadow_only"
STATUS = "research_candidate"
RECOMMENDATION = "USE_ONLY_HI_J2_G_SLOPE"
PROMOTION_STATUS = "not_promoted"

SHADOW_ARTIFACT = "artifacts/ecse_x3_b_owner_shadow_lab.jsonl"
SUMMARY_ARTIFACT = "artifacts/ecse_x3_b_owner_shadow_lab_summary.json"

REQUIRED_PROB_KEYS = (
    "ft_home",
    "ft_away",
    "ou_over_25",
    "btts_yes",
    "ou_over_15",
)

FORBIDDEN_PUBLIC_MODULES = (
    "worldcup_predictor/api/routes/predictions.py",
    "worldcup_predictor/billing/billing_service.py",
)
