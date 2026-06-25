"""Phase 60D — Elite World Cup experimental predictions API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from worldcup_predictor.admin.elite_world_cup_predictions import EliteWorldCupPredictionsService
from worldcup_predictor.api.deps import require_super_admin_user
from worldcup_predictor.config.settings import get_settings

router = APIRouter(prefix="/elite/world-cup", tags=["elite-world-cup"])
_service = EliteWorldCupPredictionsService()


@router.get("/predictions")
def elite_world_cup_predictions(
    request: Request,
    market: str = Query(default="all"),
    tier: str = Query(default="all"),
    status: str = Query(default="all", description="all | pending | evaluated"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None),
    x_super_admin_gate_token: str | None = Header(default=None, alias="X-Super-Admin-Gate-Token"),
) -> dict[str, Any]:
    """Elite experimental World Cup predictions — super_admin unless ELITE_WC_PUBLIC_ENABLED=true."""
    settings = get_settings()
    if settings.elite_wc_public_enabled:
        public_mode = True
        include_comparison = False
    else:
        require_super_admin_user(
            request,
            authorization=authorization,
            x_super_admin_gate_token=x_super_admin_gate_token,
        )
        public_mode = False
        include_comparison = True

    return _service.list_predictions(
        market=market,
        tier=tier,
        status=status,
        limit=limit,
        offset=offset,
        include_comparison=include_comparison,
        public_mode=public_mode,
    )
