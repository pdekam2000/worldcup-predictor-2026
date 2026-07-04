"""PHASE ECSE-UI-1 / OWNER-PREDICTIONS-UI-2 — Public read-only ECSE display API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from worldcup_predictor.api.deps import get_optional_current_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_match_display import build_ecse_fixture_display

router = APIRouter(prefix="/research/ecse", tags=["research-ecse"])


@router.get("/fixtures/{fixture_id}")
def ecse_fixture_display(
    fixture_id: int,
    viewer: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Top ECSE score candidates for a match (read-only, no inference)."""
    if fixture_id <= 0:
        raise HTTPException(status_code=400, detail="invalid fixture_id")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        payload = build_ecse_fixture_display(conn, fixture_id, viewer=viewer)
        # Never expose shadow preview to anonymous/public responses even if misconfigured
        if viewer is None or not payload.get("access", {}).get("can_view_shadow_preview"):
            payload.pop("shadow_preview", None)
        if viewer is None or not payload.get("access", {}).get("can_view_top5"):
            payload["top_5"] = []
            payload.pop("consistency_notes", None)
            payload.pop("engine_meta", None)
        return payload
    finally:
        conn.close()
