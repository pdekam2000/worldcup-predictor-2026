"""PHASE ECSE-ODDALERTS-3 — Owner-only ECSE OddAlerts shadow lab API."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query

from worldcup_predictor.api.deps import require_owner_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.owner.oddalerts_ecse_lab_service import EcseOddalertsOwnerLabService
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID

router = APIRouter(prefix="/owner/ecse-oddalerts-shadow", tags=["owner-ecse-oddalerts-shadow"])
_service = EcseOddalertsOwnerLabService()


def _conn() -> sqlite3.Connection:
    settings = get_settings()
    return connect(get_db_path(settings.sqlite_path))


@router.get("")
def owner_ecse_oddalerts_shadow(
    shadow_run_id: str = Query(default=DEFAULT_RUN_ID),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    competition: str | None = Query(default=None),
    team: str | None = Query(default=None),
    promotion_action: str | None = Query(default=None),
    status: str = Query(default="all"),
    top1_score: str | None = Query(default=None),
    top1_outcome: str | None = Query(default=None),
    lambda_home_min: float | None = Query(default=None),
    lambda_home_max: float | None = Query(default=None),
    lambda_away_min: float | None = Query(default=None),
    lambda_away_max: float | None = Query(default=None),
    top3_contains_actual: bool | None = Query(default=None),
    top5_contains_actual: bool | None = Query(default=None),
    bookmaker_agreement_min: float | None = Query(default=None),
    crosswalk_confidence_min: str | None = Query(default=None),
    segment_recommendation: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    conn = _conn()
    try:
        return _service.list_shadow_predictions(
            conn,
            shadow_run_id=shadow_run_id,
            date_from=date_from,
            date_to=date_to,
            competition=competition,
            team=team,
            promotion_action=promotion_action,
            status=status,
            top1_score=top1_score,
            top1_outcome=top1_outcome,
            lambda_home_min=lambda_home_min,
            lambda_home_max=lambda_home_max,
            lambda_away_min=lambda_away_min,
            lambda_away_max=lambda_away_max,
            top3_contains_actual=top3_contains_actual,
            top5_contains_actual=top5_contains_actual,
            bookmaker_agreement_min=bookmaker_agreement_min,
            crosswalk_confidence_min=crosswalk_confidence_min,
            segment_recommendation=segment_recommendation,
            limit=limit,
            offset=offset,
        )
    finally:
        conn.close()


@router.get("/monitor")
def owner_ecse_oddalerts_shadow_monitor(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status: str = Query(default="all"),
    limit: int = Query(default=200, ge=1, le=500),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    from worldcup_predictor.research.oddalerts_ecse_monitor import list_monitor_for_owner

    conn = _conn()
    try:
        return list_monitor_for_owner(
            conn,
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
        )
    finally:
        conn.close()
