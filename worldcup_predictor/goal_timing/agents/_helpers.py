"""Shared helpers for goal timing specialist agents."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


def foundation_agent_output(
    agent_name: str,
    *,
    features: dict[str, Any],
    domain_signals: dict[str, Any] | None = None,
    missing: list[str] | None = None,
) -> GoalTimingAgentOutput:
    has_data = bool(features.get("has_historical_goal_events") or features.get("provider_manifest"))
    return GoalTimingAgentOutput(
        agent_name=agent_name,
        status="available" if has_data else "limited",
        signals=domain_signals or {"foundation": True, "data_pending": not has_data},
        impact_score=0.5 if has_data else 0.2,
        missing_data=missing or ([] if has_data else ["historical_goal_events"]),
        notes="Phase 51B foundation — full provider wiring in 51C.",
    )


def feature_agent_output(
    agent_name: str,
    *,
    features: dict[str, Any],
    signals: dict[str, Any],
    impact_score: float,
    missing: list[str] | None = None,
    notes: str | None = None,
) -> GoalTimingAgentOutput:
    dq = float(features.get("data_quality_score") or 0.0)
    status = "available" if impact_score >= 0.35 and dq >= 0.4 else "limited"
    return GoalTimingAgentOutput(
        agent_name=agent_name,
        status=status,
        signals=signals,
        impact_score=round(min(1.0, max(0.0, impact_score)), 4),
        missing_data=missing or [],
        notes=notes,
    )


def dominant_range(dist: dict[str, float] | None) -> str | None:
    if not dist:
        return None
    best = max(GOAL_TIMING_MINUTE_RANGES, key=lambda k: float(dist.get(k) or 0.0))
    if float(dist.get(best) or 0.0) <= 0:
        return None
    return best


def range_entropy(dist: dict[str, float] | None) -> float:
    if not dist:
        return 1.0
    total = sum(max(0.0, float(dist.get(k) or 0.0)) for k in GOAL_TIMING_MINUTE_RANGES)
    if total <= 0:
        return 1.0
    import math

    ent = 0.0
    for k in GOAL_TIMING_MINUTE_RANGES:
        p = max(0.0, float(dist.get(k) or 0.0)) / total
        if p > 0:
            ent -= p * math.log(p)
    return round(ent, 4)
