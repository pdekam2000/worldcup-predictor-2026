"""UEFA goalscorer odds coverage audit (Phase 54Q-1)."""

from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.runner import ARTIFACT_DIR, REPORT_PATH, run_phase54q1

__all__ = ["ARTIFACT_DIR", "REPORT_PATH", "VALID_RECOMMENDATIONS", "run_phase54q1"]
