"""National team intelligence package (Phase 32B)."""

from worldcup_predictor.intelligence.national_team.integration import (
    apply_national_confidence_components,
    attach_national_team_intelligence,
    get_national_block,
    national_wde_confidence_boost,
    verify_thresholds_unchanged,
)
from worldcup_predictor.intelligence.national_team.orchestrator import (
    SUPPLEMENTAL_KEY,
    build_national_team_intelligence,
    is_world_cup_report,
)

__all__ = [
    "SUPPLEMENTAL_KEY",
    "apply_national_confidence_components",
    "attach_national_team_intelligence",
    "build_national_team_intelligence",
    "get_national_block",
    "is_world_cup_report",
    "national_wde_confidence_boost",
    "verify_thresholds_unchanged",
]
