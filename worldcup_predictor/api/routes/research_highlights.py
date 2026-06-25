"""Public research highlights API — Phase 60C."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from worldcup_predictor.research.highlights_service import load_highlights_payload

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/highlights")
def research_highlights() -> dict[str, Any]:
    """Public-safe aggregated research stats (no shadow/admin internals)."""
    return load_highlights_payload()
