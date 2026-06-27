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

    try:
        return GoalTimingPredictionService().list_today_picks(limit=min(max(limit, 1), 50))
    except Exception as exc:
        return {
            "competition_keys": [],
            "picks": [],
            "count": 0,
            "errors": [{"error": str(exc)}],
            "status": "partial",
        }


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
    """Monitoring dashboard — live picks, evaluations, accuracy, scheduler (Phase 51G)."""
    from worldcup_predictor.goal_timing.dashboard_service import GoalTimingDashboardService

    engine_status = _get_engine().foundation_status()
    monitoring = GoalTimingDashboardService().build_monitoring_dashboard()
    return {
        **engine_status,
        **monitoring,
        # Legacy keys for backward compatibility
        "picks_today": monitoring.get("upcoming_picks") or [],
        "picks_count": (monitoring.get("counts") or {}).get("upcoming_picks", 0),
        "evaluation_count": (monitoring.get("counts") or {}).get("evaluated_picks", 0),
        "accuracy_summary": {
            "sample_size": (monitoring.get("accuracy") or {}).get("sample_size", 0),
            "markets": (monitoring.get("accuracy") or {}).get("markets"),
            "overall": {
                "first_goal_team_winrate": (monitoring.get("accuracy") or {}).get("team_winrate"),
                "goal_range_winrate": (monitoring.get("accuracy") or {}).get("range_winrate"),
                "goal_minute_winrate": (monitoring.get("accuracy") or {}).get("minute_winrate"),
                "goal_minute_soft_winrate": (monitoring.get("accuracy") or {}).get("minute_soft_winrate"),
            },
        },
        "backtest_summary": None,
    }


@router.get("/history")
def goal_timing_history(
    limit: int = 50,
    offset: int = 0,
    competition_key: str | None = None,
) -> dict[str, Any]:
    """Evaluated goal-timing predictions with correct/wrong/partial status."""
    from worldcup_predictor.goal_timing.history_service import GoalTimingHistoryService

    return GoalTimingHistoryService().list_history(
        limit=min(max(limit, 1), 200),
        offset=max(offset, 0),
        competition_key=competition_key,
    )


@router.get("/accuracy")
def goal_timing_accuracy(competition_key: str | None = None) -> dict[str, Any]:
    """Aggregate winrates for First Goal Team, Goal Range, and Goal Minute markets."""
    from worldcup_predictor.goal_timing.history_service import GoalTimingHistoryService

    return GoalTimingHistoryService().accuracy_summary(competition_key=competition_key)


@router.get("/performance")
def goal_timing_performance(competition_key: str | None = None) -> dict[str, Any]:
    """Learning statistics: winrate by market, league, DQ, confidence, and predicted first-goal team."""
    from worldcup_predictor.goal_timing.history_service import GoalTimingHistoryService

    return GoalTimingHistoryService().performance_report(competition_key=competition_key)


@router.post("/evaluations/run")
def goal_timing_run_evaluations(
    limit: int = 200,
    max_api_calls: int = 50,
    refresh_first: bool = True,
) -> dict[str, Any]:
    """Run finish detection, result refresh, and evaluation for published picks."""
    from worldcup_predictor.goal_timing.evaluation_job import run_goal_timing_evaluations

    job = run_goal_timing_evaluations(
        limit=min(max(limit, 1), 500),
        refresh_first=refresh_first,
        max_api_calls=min(max(max_api_calls, 0), 100),
    )
    return job.to_dict()
