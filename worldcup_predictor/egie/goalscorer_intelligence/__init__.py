"""Goalscorer intelligence shadow layer (Phase 54P/54Q — research only)."""

from worldcup_predictor.egie.goalscorer_intelligence.models import VALID_RECOMMENDATIONS as P54P_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import VALID_RECOMMENDATIONS as P54Q_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_intelligence.runner import ARTIFACT_DIR, REPORT_PATH, run_phase54p
from worldcup_predictor.egie.goalscorer_intelligence.stress_runner import ARTIFACT_DIR as Q_ARTIFACT_DIR, REPORT_PATH as Q_REPORT_PATH, run_phase54q

__all__ = [
    "ARTIFACT_DIR",
    "Q_ARTIFACT_DIR",
    "Q_REPORT_PATH",
    "P54P_RECOMMENDATIONS",
    "P54Q_RECOMMENDATIONS",
    "REPORT_PATH",
    "run_phase54p",
    "run_phase54q",
]
