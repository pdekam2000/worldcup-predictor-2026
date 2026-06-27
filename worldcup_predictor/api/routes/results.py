"""Evaluated prediction results — Hotfix Pack 3 visibility API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query

from worldcup_predictor.api.evaluated_results import list_evaluated_results
from worldcup_predictor.config.settings import get_settings

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/evaluated")
def get_evaluated_results(
    range: str = Query(default="all", description="yesterday | 7d | 30d | all"),
    status: str = Query(default="all", description="correct | wrong | partial | pending | all"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    competition: str = Query(default="all", description="Competition key or all"),
    utc_offset_minutes: int | None = Query(
        default=None,
        description="Client local offset from UTC in minutes (-Date.getTimezoneOffset())",
    ),
    market: str = Query(default="all", description="Market filter key or best_bets"),
) -> dict[str, Any]:
    """Public read-only list of evaluated predictions with scores and market breakdown."""
    comp = None if competition in {"all", "*", ""} else competition
    return list_evaluated_results(
        settings=get_settings(),
        range_key=range,
        status_filter=status,
        market_filter=market,
        limit=limit,
        offset=offset,
        competition_key=comp,
        utc_offset_minutes=utc_offset_minutes,
    )
