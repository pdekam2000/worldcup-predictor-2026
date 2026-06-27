"""PredOps read APIs — Phase A15."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from worldcup_predictor.api.deps import require_owner_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.predops.combo_readiness import build_combo_readiness_report
from worldcup_predictor.predops.coverage import build_predops_coverage_report
from worldcup_predictor.predops.public_sanitize import sanitize_public_coverage, sanitize_public_snapshot
from worldcup_predictor.predops.store import PredOpsStore

router = APIRouter(prefix="/predops", tags=["predops"])


@router.get("/coverage")
def predops_coverage_public(
    window_days: int = Query(default=7, ge=1, le=14),
) -> dict[str, Any]:
    report = build_predops_coverage_report(window_days=window_days)
    return sanitize_public_coverage(report)


@router.get("/coverage/admin")
def predops_coverage_admin(
    window_days: int = Query(default=7, ge=1, le=14),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    return build_predops_coverage_report(window_days=window_days)


@router.get("/queue")
def predops_queue_admin(
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = Query(default=None),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    store = PredOpsStore()
    return {
        "status": "ok",
        "stats": store.queue_stats(),
        "jobs": store.list_queue(limit=limit, status=status),
        "last_run": store.last_scheduler_run(),
    }


@router.get("/snapshots/latest")
def predops_snapshot_latest(
    fixture_id: int = Query(..., ge=1),
) -> dict[str, Any]:
    store = PredOpsStore()
    snap = store.get_latest_snapshot(fixture_id)
    return {"status": "ok", "snapshot": sanitize_public_snapshot(snap)}


@router.get("/snapshots/history")
def predops_snapshot_history_admin(
    fixture_id: int = Query(..., ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    store = PredOpsStore()
    return {
        "status": "ok",
        "fixture_id": fixture_id,
        "history": store.list_snapshot_history(fixture_id, limit=limit),
    }


@router.get("/combo-readiness")
def predops_combo_readiness(
    min_confidence: float = Query(default=55.0, ge=0, le=100),
) -> dict[str, Any]:
    return build_combo_readiness_report(min_confidence=min_confidence)


@router.post("/run-once")
def predops_run_once_admin(
    window_days: int = Query(default=7, ge=1, le=14),
    max_jobs: int = Query(default=12, ge=0, le=100),
    dry_run: bool = Query(default=False),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    from worldcup_predictor.predops.scheduler import run_predops_scheduler_once

    return run_predops_scheduler_once(window_days=window_days, max_jobs=max_jobs, dry_run=dry_run)
