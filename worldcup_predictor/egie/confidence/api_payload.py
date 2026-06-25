"""Public API shape for hybrid confidence (Phase 52E)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.confidence.models import HybridConfidenceResult
from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES

TIER_RELIABILITY: dict[str, str] = {
    "A": "high",
    "B": "medium",
    "C": "low",
    "D": "insufficient",
}


def build_probability_bar(range_probs: dict[str, float] | None) -> list[dict[str, Any]]:
    probs = range_probs or {}
    return [
        {
            "bucket": bucket,
            "probability": round(float(probs.get(bucket) or 0.0), 4),
        }
        for bucket in GOAL_TIMING_MINUTE_RANGES
    ]


def format_hybrid_confidence_api(
    hybrid: HybridConfidenceResult,
    *,
    range_probs: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Serialize hybrid confidence for REST responses — no raw % as primary trust signal."""
    scores = hybrid.scores
    tiers = hybrid.tiers
    ui = hybrid.ui
    return {
        "team": {
            "score": scores.conf_team,
            "tier": tiers.team_tier,
            "label": ui.team_badge,
            "reliability": TIER_RELIABILITY.get(tiers.team_tier, "low"),
            "reliability_tier": f"Tier {tiers.team_tier}",
        },
        "range": {
            "score": scores.conf_range,
            "tier": tiers.range_tier,
            "reliability": TIER_RELIABILITY.get(tiers.range_tier, "low"),
            "reliability_tier": f"Tier {tiers.range_tier}",
            "probability_bar": build_probability_bar(range_probs),
        },
        "minute": {
            "score": scores.conf_minute,
            "tier": tiers.minute_tier,
            "label": ui.minute_label,
            "badge": ui.minute_badge,
            "experimental": True,
        },
        "display_tier": tiers.display_tier,
        "model_version": hybrid.model_version,
    }
