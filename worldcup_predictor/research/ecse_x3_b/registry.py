"""PHASE ECSE-X3-B — Shadow candidate registry."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x3_b.constants import (
    CANDIDATE_ID,
    DISPLAY_LABEL,
    MODE,
    PROMOTION_STATUS,
    RECOMMENDATION,
    STATUS,
)

SHADOW_CANDIDATE_REGISTRY: dict[str, dict[str, Any]] = {
    CANDIDATE_ID: {
        "id": CANDIDATE_ID,
        "display_label": DISPLAY_LABEL,
        "mode": MODE,
        "status": STATUS,
        "recommendation": RECOMMENDATION,
        "promotion_status": PROMOTION_STATUS,
        "method": "j2_g_slope",
        "signals": ("J2", "G", "ou_slope"),
        "phi_forbidden": True,
    },
}

# Full composite challengers are research-only (X3-A); not registered for promotion.
COMPOSITE_PROMOTION_BLOCKED = (
    "composite_full",
    "conservative_composite",
    "segment_aware",
    "hi_only",
    "zz2_only",
)


def get_registry() -> dict[str, Any]:
    return {
        "candidates": list(SHADOW_CANDIDATE_REGISTRY.values()),
        "composite_promotion_blocked": list(COMPOSITE_PROMOTION_BLOCKED),
        "active_candidate": CANDIDATE_ID,
    }
