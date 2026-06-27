"""Phase A23 — prediction lifecycle archive APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.lifecycle.scheduler import run_lifecycle_evaluation_cycle
from worldcup_predictor.lifecycle.service import (
    get_fixture_lifecycle_detail,
    get_market_accuracy_stats,
    search_archive,
)

router = APIRouter(tags=["prediction-lifecycle"])
admin_router = APIRouter(tags=["prediction-lifecycle-admin"])


@router.get("/lifecycle/archive/search")
def api_lifecycle_search(
    team: str | None = None,
    competition_key: str | None = None,
    season: int | None = None,
    market: str | None = None,
    lifecycle_state: str | None = None,
    tier: str | None = None,
    model_version: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    min_bet_quality: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return search_archive(
        team=team,
        competition_key=competition_key,
        season=season,
        market=market,
        lifecycle_state=lifecycle_state,
        tier=tier,
        model_version=model_version,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
        min_bet_quality=min_bet_quality,
        limit=limit,
        offset=offset,
    )


@router.get("/lifecycle/fixture/{fixture_id}")
def api_lifecycle_fixture_detail(
    fixture_id: int,
    _user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return get_fixture_lifecycle_detail(fixture_id)


@router.get("/lifecycle/market-accuracy")
def api_lifecycle_market_accuracy(
    _user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return get_market_accuracy_stats()


@admin_router.post("/admin/lifecycle/evaluate")
def api_lifecycle_evaluate_cycle(
    limit: int = Query(default=100, ge=1, le=500),
    _user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = run_lifecycle_evaluation_cycle(limit=limit)
    return {
        "status": "ok",
        "scanned": result.scanned,
        "evaluated": result.evaluated,
        "skipped": result.skipped,
        "errors": result.errors,
    }
