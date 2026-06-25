"""Goalscorer shadow engine (Phase 54K — research only)."""

from worldcup_predictor.egie.goalscorer_shadow.backtest import run_backtest
from worldcup_predictor.egie.goalscorer_shadow.calibration import apply_calibration, calibration_summary
from worldcup_predictor.egie.goalscorer_shadow.dataset_builder import ARTIFACT_DIR, GoalscorerDatasetBuilder
from worldcup_predictor.egie.goalscorer_shadow.feature_builder import GoalscorerFeatureBuilder
from worldcup_predictor.egie.goalscorer_shadow.models import BacktestReport, VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_shadow.scoring import apply_baseline_scores
from worldcup_predictor.egie.goalscorer_shadow.validation import align_odds_with_model

__all__ = [
    "ARTIFACT_DIR",
    "BacktestReport",
    "GoalscorerDatasetBuilder",
    "GoalscorerFeatureBuilder",
    "VALID_RECOMMENDATIONS",
    "align_odds_with_model",
    "apply_calibration",
    "apply_baseline_scores",
    "calibration_summary",
    "run_backtest",
]
