"""Goalscorer ML shadow engine (Phase 54L — research only)."""

from worldcup_predictor.egie.goalscorer_ml_shadow.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_ml_shadow.runner import ARTIFACT_DIR, run_ml_shadow

__all__ = ["ARTIFACT_DIR", "VALID_RECOMMENDATIONS", "run_ml_shadow"]
