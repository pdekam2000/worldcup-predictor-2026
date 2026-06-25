"""Part C — component blame matrix (helped / hurt / neutral / uncertain)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.root_cause.models import BlameLabel, ComponentBlame, MarketComparison


def _pick_matches(prediction: Any, reality: Any) -> bool | None:
    if prediction is None or reality is None:
        return None
    if isinstance(prediction, list):
        return str(reality) in [str(p) for p in prediction]
    return str(prediction).lower() == str(reality).lower()


def classify_component_blame(
    contribution: dict[str, Any],
    *,
    reality: Any,
    fusion_correct: bool,
) -> ComponentBlame:
    cid = str(contribution.get("component_id") or "unknown")
    pred = contribution.get("prediction")
    weight = float(contribution.get("weight") or 0.0)
    conf = float(contribution.get("confidence") or 0.5)
    match = _pick_matches(pred, reality)

    label: BlameLabel = "neutral"
    if pred is None:
        label = "neutral"
    elif match is True:
        label = "helped" if fusion_correct or weight >= 0.15 else "uncertain"
    elif match is False:
        label = "hurt" if weight >= 0.2 else "uncertain"
    else:
        label = "neutral"

    return ComponentBlame(
        component_id=cid,
        label=label,
        weight=round(weight, 4),
        component_confidence=round(conf, 4),
        prediction=pred,
    )


def blame_row(
    comparison: MarketComparison,
    contributions: list[dict[str, Any]],
) -> list[ComponentBlame]:
    fusion_correct = comparison.outcome == "correct"
    return [
        classify_component_blame(c, reality=comparison.reality, fusion_correct=fusion_correct)
        for c in contributions
        if c.get("component_id")
    ]


def aggregate_blame_matrix(
    rows: list[tuple[MarketComparison, list[ComponentBlame]]],
) -> dict[str, Any]:
    """Aggregate blame percentages by league, market, season."""
    buckets: dict[str, dict[str, dict[str, int]]] = {}

    def _key(league: int | None, market: str, season: int | None) -> str:
        return f"league={league or 'all'}|market={market}|season={season or 'all'}"

    for comparison, blames in rows:
        k = _key(comparison.league_id, comparison.market_id, comparison.season_id)
        bucket = buckets.setdefault(k, {})
        for b in blames:
            comp_bucket = bucket.setdefault(b.component_id, {"helped": 0, "hurt": 0, "neutral": 0, "uncertain": 0})
            comp_bucket[b.label] += 1

    matrix: dict[str, Any] = {}
    for k, comps in buckets.items():
        matrix[k] = {}
        for cid, counts in comps.items():
            total = sum(counts.values()) or 1
            matrix[k][cid] = {
                label: round(counts[label] / total, 4)
                for label in ("helped", "hurt", "neutral", "uncertain")
            }
            matrix[k][cid]["n"] = total

    # Global rollup by component
    global_counts: dict[str, dict[str, int]] = {}
    for _, blames in rows:
        for b in blames:
            g = global_counts.setdefault(b.component_id, {"helped": 0, "hurt": 0, "neutral": 0, "uncertain": 0})
            g[b.label] += 1

    global_pct: dict[str, Any] = {}
    for cid, counts in global_counts.items():
        total = sum(counts.values()) or 1
        global_pct[cid] = {label: round(counts[label] / total, 4) for label in counts}
        global_pct[cid]["n"] = total
        global_pct[cid]["hurt_rate"] = round(counts["hurt"] / total, 4)
        global_pct[cid]["help_rate"] = round(counts["helped"] / total, 4)

    return {"by_segment": matrix, "global": global_pct}
