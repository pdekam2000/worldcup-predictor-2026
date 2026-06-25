"""Public accuracy dashboard routes — Phase 42B."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from worldcup_predictor.api.public_accuracy_summary import build_public_accuracy_summary

router = APIRouter(prefix="/accuracy", tags=["accuracy"])


@router.get("/summary")
def accuracy_summary(
    competition: str = Query(default="world_cup_2026"),
) -> dict[str, Any]:
    """Platform-wide accuracy aggregates (no auth, no admin internals)."""
    return build_public_accuracy_summary(competition_key=competition)
