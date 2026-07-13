"""Last-8 team goal form audit and ECSE Top5 coverage shadow (research only)."""

from worldcup_predictor.research.last8_team_form.profile_builder import build_team_last8_goal_profile
from worldcup_predictor.research.last8_team_form.coverage_diagnostics import diagnose_top5_coverage
from worldcup_predictor.research.last8_team_form.scenario_profile import build_shadow_scenario_profile
from worldcup_predictor.research.last8_team_form.shadow_selector import (
    select_baseline_top5,
    select_wde_aligned_top5,
    select_scenario_diversified_top5,
    select_last8_aware_top5,
    select_hybrid_top5,
    select_top3_variants,
)

SHADOW_ONLY = True
PUBLIC_PUBLISH = False
PHASE = "LAST8-TEAM-FORM-ECSE-SHADOW-1"

__all__ = [
    "SHADOW_ONLY",
    "PUBLIC_PUBLISH",
    "PHASE",
    "build_team_last8_goal_profile",
    "diagnose_top5_coverage",
    "build_shadow_scenario_profile",
    "select_baseline_top5",
    "select_wde_aligned_top5",
    "select_scenario_diversified_top5",
    "select_last8_aware_top5",
    "select_hybrid_top5",
    "select_top3_variants",
]
