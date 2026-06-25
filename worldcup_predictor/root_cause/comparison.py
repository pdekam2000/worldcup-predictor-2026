"""Part A — post-match prediction vs reality comparison."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.root_cause.models import MarketComparison


def _fusion_pick(market_id: str, prediction: Any) -> Any:
    if market_id == "1x2" and isinstance(prediction, dict):
        return max(prediction, key=prediction.get)
    return prediction


def compare_evaluation_row(row: dict[str, Any], *, fixture_meta: dict[str, Any] | None = None) -> MarketComparison | None:
    outcome = str(row.get("outcome") or "")
    if outcome in ("pending", "abstain"):
        return None
    meta = fixture_meta or {}
    prediction = row.get("prediction")
    reality = row.get("reality")
    return MarketComparison(
        fixture_id=int(row.get("fixture_id") or 0),
        market_id=str(row.get("market_id") or ""),
        prediction=_fusion_pick(str(row.get("market_id") or ""), prediction),
        reality=reality,
        confidence=float(row.get("confidence") or 0.0),
        tier=str(row.get("tier") or "C"),
        outcome=outcome,
        league_id=meta.get("league_id"),
        season_id=meta.get("season_id"),
        competition_key=meta.get("competition_key"),
    )


def compare_evaluations(
    rows: list[dict[str, Any]],
    *,
    fixture_lookup: dict[int, dict[str, Any]] | None = None,
) -> list[MarketComparison]:
    lookup = fixture_lookup or {}
    out: list[MarketComparison] = []
    for row in rows:
        fid = int(row.get("fixture_id") or 0)
        cmp = compare_evaluation_row(row, fixture_meta=lookup.get(fid))
        if cmp:
            out.append(cmp)
    return out


def summarize_comparisons(comparisons: list[MarketComparison]) -> dict[str, Any]:
    by_market: dict[str, dict[str, int]] = {}
    by_tier: dict[str, dict[str, int]] = {}
    for c in comparisons:
        mb = by_market.setdefault(c.market_id, {"correct": 0, "incorrect": 0, "total": 0})
        mb["total"] += 1
        if c.outcome == "correct":
            mb["correct"] += 1
        else:
            mb["incorrect"] += 1
        tb = by_tier.setdefault(c.tier, {"correct": 0, "incorrect": 0, "total": 0})
        tb["total"] += 1
        if c.outcome == "correct":
            tb["correct"] += 1
        else:
            tb["incorrect"] += 1

    market_acc = {
        mk: round(v["correct"] / v["total"], 4) if v["total"] else 0.0
        for mk, v in by_market.items()
    }
    return {
        "total_comparisons": len(comparisons),
        "by_market": by_market,
        "market_accuracy": market_acc,
        "by_tier": by_tier,
    }
