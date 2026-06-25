"""Phase 33 — background World Cup prediction + auto evaluation."""

from worldcup_predictor.automation.worldcup_background.auto_evaluation_job import run_production_auto_evaluation
from worldcup_predictor.automation.worldcup_background.result_evaluation_job import run_evaluate_worldcup_results
from worldcup_predictor.automation.worldcup_background.runner import (
    run_daily_worldcup_predict,
    run_evaluate_worldcup_results_cli,
    run_worldcup_auto_cycle,
)

__all__ = [
    "run_daily_worldcup_predict",
    "run_evaluate_worldcup_results",
    "run_evaluate_worldcup_results_cli",
    "run_production_auto_evaluation",
    "run_worldcup_auto_cycle",
]