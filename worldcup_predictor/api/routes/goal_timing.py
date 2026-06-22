"""Phase 51 — Elite Goal Timing engine API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine

router = APIRouter(prefix="/goal-timing", tags=["goal-timing"])

_engine: EliteGoalTimingEngine | None = None


def _get_engine() -> EliteGoalTimingEngine:
    global _engine
    if _engine is None:
        _engine = EliteGoalTimingEngine()
    return _engine


@router.get("/status")
def goal_timing_status() -> dict[str, Any]:
    """Engine status — phase, agents, prediction leagues."""
    return _get_engine().foundation_status()


@router.get("/features/{fixture_id}")
def goal_timing_features_probe(
    fixture_id: int,
    persist: bool = False,
) -> dict[str, Any]:
    """Build real goal timing features for one fixture (stored data; no API quota by default)."""
    from worldcup_predictor.goal_timing.service import GoalTimingFeatureService

    service = GoalTimingFeatureService()
    return service.probe_fixture_report(fixture_id, persist=persist)


@router.get("/coverage")
def goal_timing_coverage() -> dict[str, Any]:
    from worldcup_predictor.goal_timing.service import GoalTimingFeatureService

    return GoalTimingFeatureService().coverage_report()


@router.get("/picks")
def goal_timing_picks(limit: int = 20) -> dict[str, Any]:
    """Premier League goal-timing picks for upcoming fixtures (Phase 51D)."""
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    return GoalTimingPredictionService().list_today_picks(limit=min(max(limit, 1), 50))


@router.post("/predictions/{fixture_id}")
def goal_timing_predict_fixture(fixture_id: int, persist: bool = True) -> dict[str, Any]:
    """Generate and optionally persist a goal-timing prediction for one fixture."""
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    result = GoalTimingPredictionService().predict_fixture(fixture_id, persist=persist)
    if result.get("error") == "invalid_fixture_id":
        raise HTTPException(status_code=400, detail="invalid_fixture_id")
    if result.get("error") == "league_not_enabled_for_predictions":
        raise HTTPException(status_code=422, detail=result)
    return result


@router.get("/predictions/{fixture_id}")
def goal_timing_get_prediction(fixture_id: int) -> dict[str, Any]:
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    service = GoalTimingPredictionService()
    row = service.repository.get_prediction_by_fixture(fixture_id)
    if row:
        return {"fixture_id": fixture_id, "prediction": service._serialize_prediction_row(row), "source": "stored"}
    generated = service.predict_fixture(fixture_id, persist=True)
    if generated.get("error"):
        raise HTTPException(status_code=404, detail=generated.get("error"))
    return {**generated, "source": "generated"}


@router.get("/dashboard")
def goal_timing_dashboard() -> dict[str, Any]:
    """Dashboard payload with engine status and today's picks."""
    from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService

    status = _get_engine().foundation_status()
    picks_payload = GoalTimingPredictionService().list_today_picks(limit=12)
    return {
        **status,
        "picks_today": picks_payload.get("picks") or [],
        "picks_count": picks_payload.get("count", 0),
        "recent_evaluations": [],
        "backtest_summary": None,
    }
