"""Admin Accuracy Center + Learning Dashboard routes — Phase 34."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.admin.accuracy_center import get_fixture_inspector, list_accuracy_center_rows
from worldcup_predictor.admin.learning_engine import (
    build_learning_dashboard,
    generate_and_store_learning_report,
    list_learning_reports,
)
from worldcup_predictor.api.deps import require_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

router = APIRouter(prefix="/admin/accuracy", tags=["admin-accuracy"])


@router.get("/summary")
def admin_accuracy_summary(
    competition: str = Query(default="world_cup_2026"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    data = list_accuracy_center_rows(competition_key=competition, limit=0, offset=0)
    return {
        "status": "ok",
        "competition_key": competition,
        "statistics": data["statistics"],
    }


@router.get("/evaluations")
def admin_accuracy_evaluations(
    competition: str = Query(default="world_cup_2026"),
    status: str = Query(default="all"),
    pick_tier: str = Query(default="all"),
    confidence_min: float | None = Query(default=None),
    confidence_max: float | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return list_accuracy_center_rows(
        competition_key=competition,
        status_filter=status,
        pick_tier_filter=pick_tier,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/fixtures/{fixture_id}")
def admin_fixture_inspector(
    fixture_id: int,
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    detail = get_fixture_inspector(fixture_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No stored prediction for this fixture")
    return detail


@router.post("/rebuild")
def admin_rebuild_accuracy(
    competition: str = Query(default="world_cup_2026"),
    evaluate: bool = Query(default=False),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    settings = get_settings()
    evaluated = None
    if evaluate:
        from worldcup_predictor.automation.worldcup_background.result_evaluation_job import run_evaluate_worldcup_results

        evaluated = run_evaluate_worldcup_results(settings=settings, competition_key=competition)
    from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary

    summary = rebuild_accuracy_summary(settings=settings, competition_key=competition)
    return {
        "status": "ok",
        "competition_key": competition,
        "summary": summary,
        "evaluation_job": {
            "scanned": evaluated.scanned if evaluated else 0,
            "evaluated": evaluated.evaluated if evaluated else 0,
            "errors": evaluated.errors if evaluated else 0,
        } if evaluated else None,
    }


@router.get("/audit")
def admin_accuracy_audit(
    competition: str = Query(default="world_cup_2026"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    """Phase 34 Part 7 — storage audit for predictions, evaluations, summaries, reports."""
    repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
    stored = repo.count_worldcup_stored_predictions(competition_key=competition)
    evals = repo.count_worldcup_prediction_evaluations_filtered(competition_key=competition)
    reports = repo.list_learning_reports(competition_key=competition, limit=1000)
    summary = repo.get_worldcup_accuracy_summary(competition_key=competition)

    dup = repo._conn.execute(
        """
        SELECT fixture_id, COUNT(*) AS c FROM worldcup_stored_predictions
        WHERE competition_key = ? GROUP BY fixture_id HAVING c > 1
        """,
        (competition,),
    ).fetchall()

    return {
        "status": "ok",
        "stored_predictions": stored,
        "evaluations": evals,
        "accuracy_summary_present": summary is not None,
        "learning_reports_count": len(reports),
        "duplicate_stored_rows": len(dup),
        "healthy": len(dup) == 0,
    }


learning_router = APIRouter(prefix="/admin/learning", tags=["admin-learning"])


@learning_router.get("/dashboard")
def admin_learning_dashboard(
    competition: str = Query(default="world_cup_2026"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return build_learning_dashboard(competition_key=competition)


@learning_router.get("/optimization")
def admin_accuracy_optimization(
    competition: str = Query(default="world_cup_2026"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    from worldcup_predictor.admin.accuracy_optimization import build_accuracy_optimization_report

    return build_accuracy_optimization_report(competition_key=competition)


@learning_router.post("/reports/generate")
def admin_generate_learning_report(
    competition: str = Query(default="world_cup_2026"),
    version: str = Query(default="v2"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return generate_and_store_learning_report(competition_key=competition, version=version)


@learning_router.get("/reports")
def admin_list_learning_reports(
    competition: str = Query(default="world_cup_2026"),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    reports = list_learning_reports(competition_key=competition, limit=limit)
    return {"status": "ok", "reports": reports, "count": len(reports)}
