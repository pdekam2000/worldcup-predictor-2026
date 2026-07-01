"""PHASE ECSE-X2-M8 — Owner-only ECSE shadow lab."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.api.deps import require_owner_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m8.lab_service import EcseOwnerShadowLabService

router = APIRouter(prefix="/owner/ecse-shadow-lab", tags=["owner-ecse-shadow-lab"])
_service = EcseOwnerShadowLabService()


def _conn() -> sqlite3.Connection:
    settings = get_settings()
    return connect(get_db_path(settings.sqlite_path))


@router.get("/summary")
def owner_ecse_shadow_lab_summary(
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    conn = _conn()
    try:
        return _service.summary(conn)
    finally:
        conn.close()


@router.get("/fixtures")
def owner_ecse_shadow_lab_fixtures(
    filter: str = Query(default="all", alias="filter"),
    league: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    conn = _conn()
    try:
        return _service.list_fixtures(
            conn,
            filter_key=filter,
            league=league,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    finally:
        conn.close()


@router.get("/fixtures/{fixture_id}")
def owner_ecse_shadow_lab_fixture_detail(
    fixture_id: int,
    _owner: WebAuthUser = Depends(require_owner_user),
) -> dict[str, Any]:
    conn = _conn()
    try:
        detail = _service.get_fixture(conn, fixture_id)
    finally:
        conn.close()
    if detail is None:
        raise HTTPException(status_code=404, detail="No shadow lab row for fixture")
    return detail
