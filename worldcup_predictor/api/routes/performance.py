"""Phase 42D — public performance + best tips routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from worldcup_predictor.api.performance_center import build_best_tips, build_performance_summary
from worldcup_predictor.monitoring.production_accuracy_monitor import build_monitoring_bundle

router = APIRouter(tags=["performance"])


@router.get("/performance/monitoring")
def performance_monitoring(
    competition: str = Query(default="world_cup_2026"),
) -> dict[str, Any]:
    """Phase 48A — trends, Rule A impact, agent contribution, leaderboard."""
    return build_monitoring_bundle(competition_key=competition)


@router.get("/performance/summary")
def performance_summary(
    competition: str = Query(default="world_cup_2026"),
) -> dict[str, Any]:
    """Real evaluated performance — market winrates with sample sizes."""
    return build_performance_summary(competition_key=competition)


@router.get("/best-tips")
def best_tips(
    competition: str = Query(default="world_cup_2026"),
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, Any]:
    """Top upcoming tips scored by historical market accuracy + confidence."""
    return build_best_tips(competition_key=competition, limit=limit)
