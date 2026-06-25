"""Phase 59A — Admin-only Elite Shadow preview endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService
from worldcup_predictor.api.deps import require_super_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser

router = APIRouter(prefix="/admin/elite-shadow", tags=["admin-elite-shadow"])
_service = EliteShadowPreviewService()
_comparison = EliteShadowComparisonService(preview=_service)


@router.get("/predictions")
def admin_elite_shadow_predictions(
    market: str = Query(default="all"),
    tier: str = Query(default="all"),
    status: str = Query(default="all", description="all | pending | evaluated"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    return _service.list_predictions(market=market, tier=tier, status=status, limit=limit, offset=offset)


@router.get("/predictions/{fixture_id}")
def admin_elite_shadow_fixture(
    fixture_id: int,
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    detail = _service.get_fixture(fixture_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No shadow predictions for this fixture")
    return detail


@router.get("/evaluations")
def admin_elite_shadow_evaluations(
    outcome: str = Query(default="all"),
    market: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    return _service.list_evaluations(outcome=outcome, market=market, limit=limit, offset=offset)


@router.get("/root-cause")
def admin_elite_shadow_root_cause(
    fixture_id: int | None = Query(default=None),
    market: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    return _service.list_root_cause(fixture_id=fixture_id, market=market, limit=limit, offset=offset)


@router.get("/summary")
def admin_elite_shadow_summary(
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    """Internal summary for admin dashboard / validation."""
    return _service.preview_summary()


@router.get("/comparison")
def admin_elite_shadow_comparison(
    market: str = Query(default="all"),
    tier: str = Query(default="all"),
    status: str = Query(default="all", description="all | pending | evaluated"),
    disagreement_only: bool = Query(default=False),
    fixture_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    """Shadow vs production comparison — super_admin only."""
    return _comparison.build_comparison(
        market=market,
        tier=tier,
        status=status,
        disagreement_only=disagreement_only,
        fixture_id=fixture_id,
        limit=limit,
        offset=offset,
    )
