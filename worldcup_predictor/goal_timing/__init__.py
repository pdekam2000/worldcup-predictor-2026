"""Phase 51 — Elite Goal Timing Intelligence Engine (independent from 1X2 pipeline)."""

from worldcup_predictor.goal_timing.config import (
    GOAL_TIMING_MINUTE_RANGES,
    GOAL_TIMING_MODEL_VERSION,
    MIN_DATA_QUALITY_FOR_PREDICTION,
)
from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine
from worldcup_predictor.goal_timing.models import GoalTimingPredictionResult

__all__ = [
    "EliteGoalTimingEngine",
    "GoalTimingPredictionResult",
    "GOAL_TIMING_MINUTE_RANGES",
    "GOAL_TIMING_MODEL_VERSION",
    "MIN_DATA_QUALITY_FOR_PREDICTION",
]
