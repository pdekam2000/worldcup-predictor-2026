"""Phase 61 — Unified hybrid prediction API (admin-gated by default)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.api.deps import get_optional_current_user, require_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.unified_hybrid.backtest import run_comparative_backtest
from worldcup_predictor.unified_hybrid.engine import UnifiedHybridPredictionEngine

router = APIRouter(prefix="/unified", tags=["unified-hybrid"])
_engine = UnifiedHybridPredictionEngine()


def _access_allowed(user: WebAuthUser | None, *, public: bool = False) -> bool:
    settings = get_settings()
    if not settings.unified_engine_enabled and not settings.unified_engine_admin_preview:
        return False
    if public and settings.unified_engine_public and settings.unified_engine_enabled:
        return True
    if user and user.role in ("admin", "super_admin", "owner"):
        return settings.unified_engine_admin_preview or settings.unified_engine_enabled
    return False


@router.get("/status")
def unified_engine_status(
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "unified_engine_enabled": settings.unified_engine_enabled,
        "unified_engine_admin_preview": settings.unified_engine_admin_preview,
        "unified_engine_public": settings.unified_engine_public,
        "unified_engine_compare_mode": settings.unified_engine_compare_mode,
        "admin_access": _access_allowed(user),
        "version": "61-v1",
    }


@router.get("/predict/{fixture_id}")
def unified_predict(
    fixture_id: int,
    competition: str | None = Query(default=None),
    compare: bool = Query(default=False),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    if not _access_allowed(user, public=settings.unified_engine_public):
        raise HTTPException(status_code=403, detail="Unified engine preview not available")

    if not settings.unified_engine_enabled and not settings.unified_engine_admin_preview:
        raise HTTPException(status_code=503, detail="Unified engine disabled")

    result = _engine.predict(
        int(fixture_id),
        competition_key=competition,
        include_compare=compare or settings.unified_engine_compare_mode,
    )
    return {"status": "ok", **result.to_dict()}


@router.get("/compare/{fixture_id}")
def unified_compare(
    fixture_id: int,
    competition: str | None = Query(default=None),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.unified_engine_compare_mode:
        raise HTTPException(status_code=403, detail="Compare mode disabled")

    result = _engine.predict(int(fixture_id), competition_key=competition, include_compare=True)
    return {"status": "ok", **result.to_dict()}


@router.get("/backtest/summary")
def unified_backtest_summary(
    limit: int = Query(default=200, ge=10, le=1000),
    competition: str | None = Query(default="world_cup_2026"),
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return run_comparative_backtest(limit=limit, competition_key=competition)
