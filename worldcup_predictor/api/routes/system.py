"""Phase 49A — system visibility routes (real data only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from worldcup_predictor.api.system_summary import build_system_summary

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/summary")
def system_summary(
    competition: str = Query(default="world_cup_2026"),
) -> dict[str, Any]:
    """Public system counts — archive size, evaluation status, performance snapshot meta."""
    return build_system_summary(competition_key=competition)
