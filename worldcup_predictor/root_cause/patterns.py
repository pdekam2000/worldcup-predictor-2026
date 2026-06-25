"""Part D — recurring failure pattern discovery."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.root_cause.attribution import _component_map, _odds_margin
from worldcup_predictor.root_cause.models import FailureAttribution, MarketComparison


def detect_patterns(
    comparison: MarketComparison,
    *,
    contributions: list[dict[str, Any]],
    fixture_meta: dict[str, Any] | None = None,
    attribution: FailureAttribution | None = None,
) -> list[str]:
    if comparison.outcome != "incorrect":
        return []

    meta = fixture_meta or {}
    patterns: list[str] = []
    comps = _component_map(contributions)

    if comparison.tier == "A":
        patterns.append("tier_a_failures")
    elif comparison.tier == "B":
        patterns.append("tier_b_failures")

    if comparison.confidence >= 0.7:
        patterns.append("high_confidence_miss")

    pred = str(comparison.prediction or "").lower()
    real = str(comparison.reality or "").lower()
    if pred == "away" and real == "home":
        home_rate = float(meta.get("home_goal_rate_proxy") or meta.get("home_recent_xg") or 0)
        away_rate = float(meta.get("away_goal_rate_proxy") or meta.get("away_recent_xg") or 0)
        if away_rate < home_rate:
            patterns.append("away_underdogs")

    lineup = comps.get("lineup_intelligence")
    if lineup and float(lineup.get("confidence") or 1) < 0.48:
        patterns.append("low_lineup_confidence")
    if lineup and lineup.get("prediction") is None:
        patterns.append("missing_lineup")

    margin = _odds_margin(contributions, comparison.reality)
    if margin is not None and margin >= 0.15:
        patterns.append("odds_disagreement_gt_15pct")

    hxg = meta.get("home_recent_xg")
    axg = meta.get("away_recent_xg")
    if hxg is None or axg is None:
        patterns.append("missing_xg")

    gs = comps.get("goalscorer_intelligence")
    egie = comps.get("egie_historical_baseline")
    if gs and egie and gs.get("prediction") and egie.get("prediction"):
        if str(gs.get("prediction")) != str(egie.get("prediction")):
            patterns.append("component_conflict")

    if attribution and attribution.failure_reason == "confidence_overestimation":
        if "high_confidence_miss" not in patterns:
            patterns.append("high_confidence_miss")

    return sorted(set(patterns))


def summarize_patterns(
  pattern_rows: list[list[str]],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in pattern_rows:
        for p in row:
            counts[p] = counts.get(p, 0) + 1
    total_failures = len(pattern_rows)
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return {
        "total_incorrect": total_failures,
        "pattern_counts": dict(ranked),
        "top_patterns": [{"pattern": p, "count": c, "rate": round(c / total_failures, 4) if total_failures else 0} for p, c in ranked[:8]],
        "has_clear_patterns": bool(ranked and ranked[0][1] >= max(5, total_failures * 0.1)),
    }
