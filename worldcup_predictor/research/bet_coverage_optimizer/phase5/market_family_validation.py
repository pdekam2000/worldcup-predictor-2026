"""Insurance market-family effectiveness (research-only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _hit(scores: list[str], actual: str) -> bool:
    a = str(actual).replace(" ", "")
    return a in {str(s).replace(" ", "") for s in scores}


def run_market_family_validation(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    fam: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "usage_count": 0,
            "wins": 0,
            "stake": 0.0,
            "gross": 0.0,
            "net": 0.0,
            "inc_mass_sum": 0.0,
            "overlap_sum": 0.0,
            "rescues": 0,
            "odds_sum": 0.0,
            "odds_n": 0,
        }
    )

    for fx in fixtures:
        label = str(fx.get("insurance_market_label") or "NONE")
        family = str(fx.get("insurance_market_family") or label)
        key = f"{family}|{label}"
        b = fam[key]
        b["usage_count"] += 1
        b["label"] = label
        b["family"] = family
        exact3 = list(fx.get("exact3") or [])
        main = exact3 + list(fx.get("main_coverage_scores") or [])
        ins_scores = list(fx.get("insurance_scores") or [])
        ins = main + ins_scores
        actual = fx["actual_score"]
        won = _hit(ins_scores, actual)  # insurance leg covers actual
        if won:
            b["wins"] += 1
        if (not _hit(main, actual)) and _hit(ins, actual):
            b["rescues"] += 1
        b["inc_mass_sum"] += float(fx.get("incremental_uncovered_mass") or 0.0)
        b["overlap_sum"] += float(fx.get("primary_overlap_ratio") or 0.0)
        odd = fx.get("insurance_odds")
        if odd and float(odd) > 1.0:
            b["odds_sum"] += float(odd)
            b["odds_n"] += 1
            stake = 1.0
            b["stake"] += stake
            if won:
                gross = float(odd) * stake
                b["gross"] += gross
                b["net"] += gross - stake
            else:
                b["net"] -= stake

    rows = []
    for key, b in fam.items():
        n = b["usage_count"] or 1
        rows.append(
            {
                "key": key,
                "family": b.get("family"),
                "label": b.get("label"),
                "usage_count": b["usage_count"],
                "win_rate": round(b["wins"] / n, 8),
                "roi": round(b["net"] / b["stake"], 8) if b["stake"] else None,
                "average_incremental_coverage": round(b["inc_mass_sum"] / n, 8),
                "average_overlap": round(b["overlap_sum"] / n, 8),
                "rescue_frequency": round(b["rescues"] / n, 8),
                "rescue_count": b["rescues"],
                "average_odds": round(b["odds_sum"] / b["odds_n"], 4) if b["odds_n"] else None,
                "profit_contribution": round(b["net"], 4),
            }
        )

    rows.sort(
        key=lambda r: (
            -float(r["rescue_frequency"]),
            -float(r["average_incremental_coverage"]),
            -int(r["usage_count"]),
        )
    )
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    return {
        "research_only": True,
        "families_ranked": rows,
        "best_performing_family": rows[0] if rows else None,
        "worst_performing_family": rows[-1] if rows else None,
    }
