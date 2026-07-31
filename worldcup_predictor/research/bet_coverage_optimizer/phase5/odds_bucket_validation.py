"""Odds-bucket analysis for insurance selections (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.constants import ODDS_BUCKETS


def _bucket(odds: float) -> str | None:
    for lo, hi, name in ODDS_BUCKETS:
        if lo <= odds < hi or (name == "3.00+" and odds >= lo):
            return name
    return None


def _hit(scores: list[str], actual: str) -> bool:
    a = str(actual).replace(" ", "")
    return a in {str(s).replace(" ", "") for s in scores}


def run_odds_bucket_validation(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {
        name: {
            "n": 0,
            "coverage_hits": 0,
            "rescues": 0,
            "stake": 0.0,
            "net": 0.0,
            "main_fail": 0,
            "overlap_sum": 0.0,
            "inc_sum": 0.0,
        }
        for _, _, name in ODDS_BUCKETS
    }

    for fx in fixtures:
        odd = fx.get("insurance_odds")
        if odd is None or float(odd) <= 1.0:
            continue
        name = _bucket(float(odd))
        if not name:
            continue
        b = buckets[name]
        b["n"] += 1
        exact3 = list(fx.get("exact3") or [])
        main = exact3 + list(fx.get("main_coverage_scores") or [])
        ins = main + list(fx.get("insurance_scores") or [])
        actual = fx["actual_score"]
        if _hit(ins, actual):
            b["coverage_hits"] += 1
        if not _hit(main, actual):
            b["main_fail"] += 1
            if _hit(ins, actual):
                b["rescues"] += 1
        b["overlap_sum"] += float(fx.get("primary_overlap_ratio") or 0.0)
        b["inc_sum"] += float(fx.get("incremental_uncovered_mass") or 0.0)
        stake = 1.0
        b["stake"] += stake
        if _hit(list(fx.get("insurance_scores") or []), actual):
            b["net"] += float(odd) * stake - stake
        else:
            b["net"] -= stake

    rows = []
    for _, _, name in ODDS_BUCKETS:
        b = buckets[name]
        n = b["n"] or 1
        rows.append(
            {
                "bucket": name,
                "n": b["n"],
                "coverage": round(b["coverage_hits"] / n, 8) if b["n"] else None,
                "insurance_usefulness": round(b["rescues"] / n, 8) if b["n"] else None,
                "roi": round(b["net"] / b["stake"], 8) if b["stake"] else None,
                "failure_rate": round(b["main_fail"] / n, 8) if b["n"] else None,
                "average_overlap": round(b["overlap_sum"] / n, 8) if b["n"] else None,
                "average_incremental_mass": round(b["inc_sum"] / n, 8) if b["n"] else None,
            }
        )

    return {"research_only": True, "buckets": rows}
