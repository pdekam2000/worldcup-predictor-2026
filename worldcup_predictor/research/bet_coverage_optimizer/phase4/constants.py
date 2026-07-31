"""Phase 4 constants — research-only forward shadow audit."""

from __future__ import annotations

PHASE_NAME = "BET_COVERAGE_OPTIMIZER_PHASE4_FORWARD_SHADOW_AUDIT"
STATUS_READY = "BET_COVERAGE_OPTIMIZER_PHASE4_FORWARD_SHADOW_READY"
RESEARCH_ONLY = True
OWNER_ONLY = True
PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False
NO_PRODUCTION_DEPLOY = True

REAL_SOURCE_TYPES = frozenset(
    {
        "manual_screenshot_transcription",
        "provider_api",
        "csv_import",
    }
)
SYNTHETIC_SOURCE_MARKERS = frozenset(
    {
        "research_synthetic",
        "researchbook",
        "estimated",
        "fabricated",
        "synthetic",
    }
)
