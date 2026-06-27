"""Phase 63 — owner command center API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from worldcup_predictor.api.deps import require_owner_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.owner.platform_service import OwnerPlatformService

router = APIRouter(prefix="/owner", tags=["owner"])
_service = OwnerPlatformService()


class AutonomousRunRequest(BaseModel):
    dry_run: bool | None = None
    fixture_limit: int | None = Field(default=None, ge=1, le=50)


@router.get("/overview")
def owner_overview(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.overview()


@router.get("/monitoring")
def owner_monitoring(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.monitoring()


@router.get("/autonomous/status")
def owner_autonomous_status(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return {"status": "ok", **(_service.autonomous_status())}


@router.post("/autonomous/run-once")
def owner_autonomous_run_once(
    body: AutonomousRunRequest | None = None,
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    payload = body or AutonomousRunRequest()
    return _service.run_once(dry_run=payload.dry_run, fixture_limit=payload.fixture_limit)


@router.get("/model-center")
def owner_model_center(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.model_center()


@router.get("/performance-center")
def owner_performance_center(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.performance_center()


@router.get("/health-dashboard")
def owner_health_dashboard(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.health_dashboard()


@router.get("/research-lab")
def owner_research_lab(
    refresh: bool = Query(default=False),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    return _service.research_lab(refresh_value=refresh)


@router.get("/research-lab/summary")
def owner_research_lab_summary(
    refresh: bool = Query(default=False),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    return _service.research_lab_summary(refresh_value=refresh)


@router.get("/promotion/status")
def owner_promotion_status(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.promotion_status()


@router.get("/betting-intelligence")
def owner_betting_intelligence(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.betting_intelligence()


@router.post("/autonomous/evaluation")
def owner_autonomous_evaluation(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.run_evaluation()


@router.post("/autonomous/certification")
def owner_autonomous_certification(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.run_certification()


@router.post("/autonomous/scheduler/enable")
@router.post("/autonomous/enable-scheduler")
def owner_scheduler_enable(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.enable_scheduler()


@router.post("/autonomous/scheduler/disable")
@router.post("/autonomous/disable-scheduler")
def owner_scheduler_disable(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.disable_scheduler()


@router.get("/notifications")
def owner_notifications(_owner: WebAuthUser = Depends(require_owner_user)) -> dict[str, Any]:
    return _service.notifications()


@router.get("/prefetch/coverage")
def owner_prefetch_coverage(
    window_days: int = Query(default=7, ge=1, le=14),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report

    return build_coverage_report(window_days=window_days)


@router.post("/prefetch/run-once")
def owner_prefetch_run_once(
    window_days: int = Query(default=7, ge=1, le=14),
    max_per_cycle: int = Query(default=24, ge=1, le=100),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    from worldcup_predictor.automation.prediction_prefetch.scheduler import run_prefetch_scheduler_once

    return run_prefetch_scheduler_once(window_days=window_days, max_per_cycle=max_per_cycle)
