"""Phase 3B — GBGM underperformance forensics and controlled improvements (shadow only)."""

from __future__ import annotations

PHASE3B_STATUSES = (
    "GBGM_IMPROVED_CHALLENGER_READY",
    "GBGM_DOMAIN_LIMITED_CHALLENGER_READY",
    "GBGM_REDESIGN_REQUIRED",
    "GBGM_DATA_COVERAGE_INSUFFICIENT",
    "GBGM_PHASE3B_VALIDATION_FAILED",
)

__all__ = ["PHASE3B_STATUSES"]
