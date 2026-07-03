"""Admin read-only owner predictions — CLAUDE-OPS-1."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from worldcup_predictor.api.deps import require_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.owner.prediction_inspection import InspectionConfig, inspect_owner_predictions

router = APIRouter(prefix="/admin", tags=["admin-owner-predictions"])


@router.get("/owner-predictions")
def admin_owner_predictions(
    date: str = Query(default="today", description="today|tomorrow|yesterday|YYYY-MM-DD"),
    scope: Literal["stored", "evaluated", "pending", "all"] = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    market: Literal[
        "1x2", "btts", "over_under", "correct_score", "first_goal", "goal_minute", "all"
    ] = Query(default="all"),
    timezone: str = Query(default="Europe/Vienna"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    """Read-only stored prediction inspection. No provider calls. No DB mutation."""
    _ = _admin
    config = InspectionConfig(
        date_arg=date,
        timezone=timezone,
        scope=scope,
        limit=limit,
        market=market,
    )
    result = inspect_owner_predictions(config)
    return {"status": result.get("status", "ok"), **result}
