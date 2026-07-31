"""League-by-league validation (research-only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.phase5.historical_validation import (
    run_historical_validation,
)


def run_league_validation(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fx in fixtures:
        by_league[str(fx.get("league") or "unknown")].append(fx)

    rows = []
    for league, rows_fx in by_league.items():
        hv = run_historical_validation(rows_fx)
        cf = hv["complete_coupon_failure"]
        st = hv["strategies"]
        priced = hv["priced_subset_analysis"]
        odds = [float(f["insurance_odds"]) for f in rows_fx if f.get("insurance_odds")]
        conf = [float(f.get("confidence") or 0) for f in rows_fx]
        ent = [float(f.get("entropy") or 0) for f in rows_fx]
        rescues = int(cf.get("insurance_rescue_count") or 0)
        main_hits = st["exact3_main"]["hits"]
        ins_hits = st["exact3_main_insurance"]["hits"]
        insurance_hurts = ins_hits < main_hits
        rows.append(
            {
                "league": league,
                "fixtures": len(rows_fx),
                "coverage_rate_main": st["exact3_main"]["coverage_rate"],
                "coverage_rate_main_insurance": st["exact3_main_insurance"]["coverage_rate"],
                "coupon_survival_main": st["exact3_main"]["ticket_survival_rate"],
                "coupon_survival_main_insurance": st["exact3_main_insurance"]["ticket_survival_rate"],
                "roi": priced.get("roi"),
                "insurance_effectiveness": round(rescues / len(rows_fx), 8) if rows_fx else 0.0,
                "insurance_rescue_count": rescues,
                "average_odds": round(sum(odds) / len(odds), 4) if odds else None,
                "average_confidence": round(sum(conf) / len(conf), 6) if conf else None,
                "average_entropy": round(sum(ent) / len(ent), 6) if ent else None,
                "complete_failure_frequency_main": cf.get("main_only_all_ticket_loss_frequency"),
                "complete_failure_frequency_main_insurance": cf.get(
                    "main_plus_insurance_all_ticket_loss_frequency"
                ),
                "insurance_hurts_performance": insurance_hurts,
                "rank_score": float(st["exact3_main_insurance"]["coverage_rate"])
                + 0.1 * float(priced.get("roi") or 0.0)
                + 0.05 * (rescues / max(1, len(rows_fx))),
            }
        )

    rows.sort(key=lambda r: (-float(r["rank_score"]), -int(r["fixtures"]), r["league"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    hurts = [r["league"] for r in rows if r["insurance_hurts_performance"]]
    return {
        "research_only": True,
        "n_leagues": len(rows),
        "leagues_ranked": rows,
        "leagues_where_insurance_hurts": hurts,
        "best_league": rows[0]["league"] if rows else None,
        "worst_league": rows[-1]["league"] if rows else None,
    }
