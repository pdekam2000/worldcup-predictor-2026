"""PHASE ECSE-UI-1 — Public read-only ECSE display API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_match_display import build_ecse_fixture_display

router = APIRouter(prefix="/research/ecse", tags=["research-ecse"])


@router.get("/fixtures/{fixture_id}")
def ecse_fixture_display(fixture_id: int) -> dict[str, Any]:
    """Top ECSE exact-score distribution for a match (read-only, no inference)."""
    if fixture_id <= 0:
        raise HTTPException(status_code=400, detail="invalid fixture_id")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        return build_ecse_fixture_display(conn, fixture_id)
    finally:
        conn.close()
