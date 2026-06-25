"""Phase 61 — Admin performance certification API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from worldcup_predictor.admin.autonomous_performance import AutonomousPerformanceService
from worldcup_predictor.api.deps import require_super_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser

router = APIRouter(prefix="/admin/performance", tags=["admin-performance"])
_service = AutonomousPerformanceService()


@router.get("/certification")
def performance_certification(
    _owner: WebAuthUser = Depends(require_super_admin_user),
) -> dict[str, Any]:
    """Super_admin only — autonomous engine certification metrics."""
    return _service.certification_summary()
