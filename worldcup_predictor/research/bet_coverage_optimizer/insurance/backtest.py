"""Historical insurance backtest — research-only, no leakage.

Uses immutable frozen inputs when available; otherwise reports exclusions.
Never mixes priced monetary analysis with probability-mass-only analysis.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash_payload(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_insurance_backtest(
    fixtures: list[dict[str, Any]],
    *,
    min_fixtures: int = 100,
) -> dict[str, Any]:
    """
    Fixture dict schema (research):
      fixture_id, top_n_scores:[{score,probability}], exact3:[scores],
      main_coverage_scores:[scores], insurance_scores:[scores] (optional),
      actual_score: "h-a",
      prematch_odds_complete: bool,
      monetary: optional {exact_odds, coverage_odds, insurance_odds, stake}

    Strategies compared on probability-mass / hit rates:
      - Exact3 only
      - Exact3 + Main Coverage
      - Exact3 + Main + Insurance
      - Full125 baseline (research comparison only; not recommended)
    """
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for fx in fixtures:
        reasons = []
        if not fx.get("top_n_scores"):
            reasons.append("MISSING_TOP_N")
        if not fx.get("exact3"):
            reasons.append("MISSING_EXACT3")
        if not fx.get("actual_score"):
            reasons.append("MISSING_ACTUAL_SCORE")
        if fx.get("uses_postmatch_odds"):
            reasons.append("FUTURE_LEAKAGE_POSTMATCH_ODDS")
        if reasons:
            excluded.append({"fixture_id": fx.get("fixture_id"), "reasons": reasons})
            continue
        included.append(fx)

    input_hash = _hash_payload(
        [{"fixture_id": f.get("fixture_id"), "actual": f.get("actual_score"), "exact3": f.get("exact3")} for f in included]
    )

    def _hit(scores: list[str], actual: str) -> bool:
        return str(actual).replace(" ", "") in {str(s).replace(" ", "") for s in scores}

    strat_stats = {
        "exact3_only": {"hits": 0, "n": 0},
        "exact3_main": {"hits": 0, "n": 0},
        "exact3_main_insurance": {"hits": 0, "n": 0},
        "full_125_baseline": {"hits": 0, "n": 0},
    }
    residual_masses: list[float] = []
    priced = {"n": 0, "net": 0.0, "stake": 0.0, "gross": 0.0}
    mass_only = {"n": 0, "hits_exact3_main_ins": 0}

    for fx in included:
        actual = str(fx["actual_score"]).replace(" ", "")
        exact3 = list(fx["exact3"])
        main = list(exact3) + list(fx.get("main_coverage_scores") or [])
        ins = list(main) + list(fx.get("insurance_scores") or [])
        # Full125 baseline: treat as hit if actual in top_n union (proxy research baseline)
        topn = [str(x.get("score") if isinstance(x, dict) else x).replace(" ", "") for x in fx["top_n_scores"]]
        full125 = list(dict.fromkeys(topn))  # research proxy, not literal 125 tickets

        for key, scores in (
            ("exact3_only", exact3),
            ("exact3_main", main),
            ("exact3_main_insurance", ins),
            ("full_125_baseline", full125),
        ):
            strat_stats[key]["n"] += 1
            if _hit(scores, actual):
                strat_stats[key]["hits"] += 1

        top_map = {
            str(x.get("score") if isinstance(x, dict) else x).replace(" ", ""): float(
                (x.get("probability") if isinstance(x, dict) else 0.0) or 0.0
            )
            for x in fx["top_n_scores"]
        }
        covered = set(str(s).replace(" ", "") for s in main)
        residual = sum(p for s, p in top_map.items() if s not in covered)
        residual_masses.append(residual)

        if fx.get("prematch_odds_complete") and isinstance(fx.get("monetary"), dict):
            priced["n"] += 1
            m = fx["monetary"]
            stake = float(m.get("stake") or 1.0)
            priced["stake"] += stake
            # Simplified: if exact3_main_insurance hits, return coverage odds * stake else 0
            if _hit(ins, actual):
                odd = float(m.get("insurance_odds") or m.get("coverage_odds") or 0.0)
                gross = odd * stake if odd > 1.0 else 0.0
                priced["gross"] += gross
                priced["net"] += gross - stake
            else:
                priced["net"] -= stake
        else:
            mass_only["n"] += 1
            if _hit(ins, actual):
                mass_only["hits_exact3_main_ins"] += 1

    def _rate(block: dict[str, int]) -> float:
        return round(block["hits"] / block["n"], 8) if block["n"] else 0.0

    enough = len(included) >= int(min_fixtures)
    return {
        "research_only": True,
        "owner_only": True,
        "immutable_input_hash": input_hash,
        "requested_min_fixtures": int(min_fixtures),
        "included_fixtures": len(included),
        "excluded_fixtures": excluded,
        "enough_historical_data": enough,
        "note": (
            None
            if enough
            else f"Only {len(included)} valid frozen fixtures available; need >={min_fixtures} for primary claim."
        ),
        "strategies": {
            k: {"coverage_rate": _rate(v), "hits": v["hits"], "n": v["n"]} for k, v in strat_stats.items()
        },
        "average_residual_uncovered_mass": round(sum(residual_masses) / len(residual_masses), 8)
        if residual_masses
        else None,
        "priced_subset_analysis": {
            "n": priced["n"],
            "total_stake": round(priced["stake"], 4),
            "gross_return": round(priced["gross"], 4),
            "net_return": round(priced["net"], 4),
            "roi": round(priced["net"] / priced["stake"], 8) if priced["stake"] else None,
            "separated_from_mass_only": True,
        },
        "probability_mass_only_analysis": {
            "n": mass_only["n"],
            "exact3_main_insurance_hit_rate": round(
                mass_only["hits_exact3_main_ins"] / mass_only["n"], 8
            )
            if mass_only["n"]
            else None,
            "separated_from_priced": True,
        },
        "full_125_baseline": "research_comparison_only_not_default",
        "no_future_leakage": True,
        "prematch_only": True,
    }
