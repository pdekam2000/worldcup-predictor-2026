"""Post-match evaluation for goal timing engine (separate from legacy archive)."""

from __future__ import annotations

from datetime import datetime, timezone

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES, MINUTE_TOLERANCE_BANDS
from worldcup_predictor.goal_timing.models import GoalTimingEvaluationResult, GoalTimingEvalStatus


def minute_to_range(minute: int | None) -> str | None:
    if minute is None:
        return None
    if minute <= 15:
        return "0-15"
    if minute <= 30:
        return "16-30"
    if minute <= 45:
        return "31-45+"
    if minute <= 60:
        return "46-60"
    if minute <= 75:
        return "61-75"
    return "76-90+"


def _team_status(predicted: str | None, actual: str | None) -> GoalTimingEvalStatus:
    if not actual:
        return "pending"
    if not predicted or predicted == "none":
        return "pending"
    return "correct" if predicted == actual else "wrong"


def _range_status(predicted: str | None, actual: str | None) -> GoalTimingEvalStatus:
    if not actual:
        return "pending"
    if not predicted:
        return "pending"
    return "correct" if predicted == actual else "wrong"


def _minute_status(
    predicted_minute: float | None,
    actual_minute: int | None,
) -> GoalTimingEvalStatus:
    if actual_minute is None or predicted_minute is None:
        return "pending"
    error = abs(actual_minute - predicted_minute)
    for band, tol in MINUTE_TOLERANCE_BANDS:
        if error <= tol:
            return "correct" if band == "exact" else "partial"
    return "wrong"


def evaluate_goal_timing_prediction(
    *,
    fixture_id: int,
    prediction_id: str,
    predicted_first_goal_team: str | None,
    predicted_first_goal_time_range: str | None,
    estimated_first_goal_minute: float | None,
    actual_first_goal_team: str | None,
    actual_first_goal_minute: int | None,
) -> GoalTimingEvaluationResult:
    actual_range = minute_to_range(actual_first_goal_minute)
    if predicted_first_goal_time_range and predicted_first_goal_time_range not in GOAL_TIMING_MINUTE_RANGES:
        predicted_first_goal_time_range = minute_to_range(
            int(estimated_first_goal_minute) if estimated_first_goal_minute is not None else None
        )

    return GoalTimingEvaluationResult(
        fixture_id=fixture_id,
        prediction_id=prediction_id,
        actual_first_goal_team=actual_first_goal_team,
        actual_first_goal_minute=actual_first_goal_minute,
        actual_first_goal_time_range=actual_range,
        first_goal_team_status=_team_status(predicted_first_goal_team, actual_first_goal_team),
        time_range_status=_range_status(predicted_first_goal_time_range, actual_range),
        minute_tolerance_status=_minute_status(estimated_first_goal_minute, actual_first_goal_minute),
        evaluated_at=datetime.now(timezone.utc),
    )
