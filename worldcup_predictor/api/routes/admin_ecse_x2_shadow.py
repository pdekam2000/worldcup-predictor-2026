"""PHASE ECSE-X2-M6 — Admin-only shadow-live shortlist endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.api.deps import require_super_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.research.ecse_x2_m6.admin_service import EcseX2ShadowLiveService

router = APIRouter(prefix="/admin/ecse-x2", tags=["admin-ecse-x2-shadow"])
_service = EcseX2ShadowLiveService()


@router.get("/shadow-live-shortlists")
def admin_shadow_live_shortlists(
    status: str = Query(default="all", description="all | pending | evaluated | applied"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    return _service.list_shortlists(status=status, limit=limit, offset=offset)


@router.get("/shadow-live-shortlists-summary")
def admin_shadow_live_summary(
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    return _service.summary()


@router.get("/shadow-live-shortlists/{fixture_id}")
def admin_shadow_live_shortlist_detail(
    fixture_id: int,
    _admin: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    detail = _service.get_fixture(fixture_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No shadow-live shortlist for fixture")
    return detail
