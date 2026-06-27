"""Phase A14 — multi-competition background prediction prefetch (orchestration only)."""

from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report
from worldcup_predictor.automation.prediction_prefetch.engine import PrefetchCycleResult, run_prefetch_cycle
from worldcup_predictor.automation.prediction_prefetch.scheduler import run_prefetch_scheduler_once

__all__ = [
    "PrefetchCycleResult",
    "build_coverage_report",
    "run_prefetch_cycle",
    "run_prefetch_scheduler_once",
]
