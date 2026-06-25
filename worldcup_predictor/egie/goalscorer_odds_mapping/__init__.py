"""Goalscorer odds mapping layer (Phase 54M — research only)."""

from worldcup_predictor.egie.goalscorer_odds_mapping.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_odds_mapping.runner import ARTIFACT_DIR, run_phase54m

__all__ = ["ARTIFACT_DIR", "VALID_RECOMMENDATIONS", "run_phase54m"]
