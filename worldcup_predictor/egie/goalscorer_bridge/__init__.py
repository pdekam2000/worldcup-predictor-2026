"""API-Football goalscorer odds bridge (Phase 54O — research only)."""

from worldcup_predictor.egie.goalscorer_bridge.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_bridge.runner import ARTIFACT_DIR, REPORT_PATH, run_phase54o

__all__ = ["ARTIFACT_DIR", "REPORT_PATH", "VALID_RECOMMENDATIONS", "run_phase54o"]
