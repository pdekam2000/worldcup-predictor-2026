"""Large-scale historical strategy replay (research-only)."""

from __future__ import annotations

import math
from typing import Any


def _norm(s: str) -> str:
    return str(s).replace(" ", "")


def _hit(scores: list[str], actual: str) -> bool:
    a = _norm(actual)
    return a in {_norm(x) for x in scores}


def _profit_factor(wins: list[float], losses: list[float]) -> float | None:
    gw = sum(wins)
    gl = abs(sum(losses))
    if gl < 1e-12:
        return None if gw <= 0 else float("inf")
    return round(gw / gl, 6)


def run_historical_validation(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    strat_keys = (
        ("exact3_only", "exact3"),
        ("exact3_main", None),  # special
        ("exact3_main_insurance", None),
        ("research_125_baseline", "baseline_125_scores"),
    )

    stats = {
        k: {"hits": 0, "n": 0, "coverage_mass_sum": 0.0, "residual_sum": 0.0, "ticket_count_sum": 0}
        for k, _ in strat_keys
    }
    layer_miss = {"main_only": 0, "main_plus_insurance": 0}
    insurance_rescues = 0
    priced = {
        "n": 0,
        "stake": 0.0,
        "gross": 0.0,
        "net": 0.0,
        "wins": [],
        "losses": [],
        "equity": [],
    }
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    cal_bins: dict[str, list[tuple[float, int]]] = {"exact3": [], "main": [], "ins": []}

    coupons = []
    for i, fx in enumerate(fixtures):
        actual = fx["actual_score"]
        exact3 = list(fx.get("exact3") or [])
        main = exact3 + list(fx.get("main_coverage_scores") or [])
        ins = main + list(fx.get("insurance_scores") or [])
        base125 = list(fx.get("baseline_125_scores") or [])

        for key, scores in (
            ("exact3_only", exact3),
            ("exact3_main", main),
            ("exact3_main_insurance", ins),
            ("research_125_baseline", base125),
        ):
            stats[key]["n"] += 1
            if _hit(scores, actual):
                stats[key]["hits"] += 1
            top_map = {
                str(x.get("score")): float(x.get("probability") or 0.0)
                for x in (fx.get("top_n_scores") or [])
                if isinstance(x, dict)
            }
            score_set = {_norm(s) for s in scores}
            cov_mass = sum(p for s, p in top_map.items() if _norm(s) in score_set)
            top_mass = sum(top_map.values()) or 1e-12
            stats[key]["coverage_mass_sum"] += cov_mass / top_mass
            stats[key]["residual_sum"] += max(0.0, 1.0 - cov_mass / top_mass)
            stats[key]["ticket_count_sum"] += {
                "exact3_only": 3,
                "exact3_main": 4,
                "exact3_main_insurance": 5,
                "research_125_baseline": 125,
            }[key]

        main_miss = not _hit(main, actual)
        ins_miss = not _hit(ins, actual)
        if main_miss:
            layer_miss["main_only"] += 1
        if ins_miss:
            layer_miss["main_plus_insurance"] += 1
        if main_miss and not ins_miss:
            insurance_rescues += 1

        # calibration: predicted mass of selected layer vs hit
        top_map = {str(x["score"]): float(x["probability"] or 0) for x in (fx.get("top_n_scores") or [])}
        p_exact = sum(top_map.get(s, 0.0) for s in exact3)
        p_main = sum(top_map.get(s, 0.0) for s in main)
        p_ins = sum(top_map.get(s, 0.0) for s in ins)
        cal_bins["exact3"].append((p_exact, 1 if _hit(exact3, actual) else 0))
        cal_bins["main"].append((p_main, 1 if _hit(main, actual) else 0))
        cal_bins["ins"].append((p_ins, 1 if _hit(ins, actual) else 0))

        if fx.get("prematch_odds_complete") and isinstance(fx.get("monetary"), dict):
            m = fx["monetary"]
            stake = float(m.get("stake") or 1.0)
            priced["n"] += 1
            priced["stake"] += stake
            if _hit(ins, actual):
                odd = float(m.get("insurance_odds") or m.get("coverage_odds") or 0.0)
                gross = odd * stake if odd > 1.0 else 0.0
                pnl = gross - stake
                priced["gross"] += gross
                priced["net"] += pnl
                priced["wins"].append(pnl if pnl > 0 else 0.0)
                if pnl < 0:
                    priced["losses"].append(pnl)
                equity += pnl
            else:
                priced["net"] -= stake
                priced["losses"].append(-stake)
                equity -= stake
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
            priced["equity"].append(round(equity, 4))

        if i % 3 == 2 and i >= 2:
            triple = fixtures[i - 2 : i + 1]
            main_fail = any(
                not _hit(list(t.get("exact3") or []) + list(t.get("main_coverage_scores") or []), t["actual_score"])
                for t in triple
            )
            ins_fail = any(
                not _hit(
                    list(t.get("exact3") or [])
                    + list(t.get("main_coverage_scores") or [])
                    + list(t.get("insurance_scores") or []),
                    t["actual_score"],
                )
                for t in triple
            )
            coupons.append({"main_all_lose": main_fail, "main_insurance_all_lose": ins_fail})

    n = len(fixtures) or 1
    n_coupons = len(coupons)
    main_fail_rate = sum(1 for c in coupons if c["main_all_lose"]) / n_coupons if n_coupons else None
    both_fail_rate = sum(1 for c in coupons if c["main_insurance_all_lose"]) / n_coupons if n_coupons else None

    # McNemar-style: among fixtures, discordant pairs where insurance changes outcome
    # H0: no difference. p-value via binomial mid-p approx on rescues vs reverse
    reverse = 0  # main hit, insurance somehow worse — shouldn't occur for nested sets
    for fx in fixtures:
        exact3 = list(fx.get("exact3") or [])
        main = exact3 + list(fx.get("main_coverage_scores") or [])
        ins = main + list(fx.get("insurance_scores") or [])
        mh, ih = _hit(main, fx["actual_score"]), _hit(ins, fx["actual_score"])
        if mh and not ih:
            reverse += 1
    # binomial test: P(X>=rescues) under p=0.5 for (rescues+reverse) trials
    disc = insurance_rescues + reverse
    if disc > 0:
        # two-sided exact binomial cumulative for k=rescues on n=disc
        p = 0.0
        for k in range(0, disc + 1):
            pmf = math.comb(disc, k) * (0.5**disc)
            if abs(k - disc / 2) >= abs(insurance_rescues - disc / 2):
                p += pmf
        mcnemar_p = min(1.0, p)
    else:
        mcnemar_p = 1.0

    def _pack(key: str) -> dict[str, Any]:
        s = stats[key]
        nn = s["n"] or 1
        return {
            "coverage_rate": round(s["hits"] / nn, 8),
            "hits": s["hits"],
            "n": s["n"],
            "ticket_survival_rate": round(s["hits"] / nn, 8),
            "average_coverage_mass": round(s["coverage_mass_sum"] / nn, 8),
            "average_residual_risk": round(s["residual_sum"] / nn, 8),
            "average_ticket_count": round(s["ticket_count_sum"] / nn, 4),
        }

    # calibration error = mean |pred - outcome| in decile bins for insurance layer
    def _cal_error(pairs: list[tuple[float, int]]) -> float | None:
        if not pairs:
            return None
        bins: dict[int, list[tuple[float, int]]] = {}
        for p, y in pairs:
            b = min(9, int(p * 10))
            bins.setdefault(b, []).append((p, y))
        errs = []
        for rows in bins.values():
            mp = sum(p for p, _ in rows) / len(rows)
            my = sum(y for _, y in rows) / len(rows)
            errs.append(abs(mp - my))
        return round(sum(errs) / len(errs), 8) if errs else None

    return {
        "research_only": True,
        "included_fixtures": len(fixtures),
        "strategies": {k: _pack(k) for k, _ in strat_keys},
        "complete_coupon_failure": {
            "n_coupons": n_coupons,
            "main_only_all_ticket_loss_frequency": round(main_fail_rate, 8) if main_fail_rate is not None else None,
            "main_plus_insurance_all_ticket_loss_frequency": round(both_fail_rate, 8)
            if both_fail_rate is not None
            else None,
            "insurance_reduces_complete_failure": bool(
                main_fail_rate is not None and both_fail_rate is not None and both_fail_rate < main_fail_rate
            ),
            "insurance_rescue_count": insurance_rescues,
            "fixture_layer_miss_main_only": layer_miss["main_only"],
            "fixture_layer_miss_main_plus_insurance": layer_miss["main_plus_insurance"],
        },
        "statistical_significance": {
            "test": "exact_binomial_discordant_pairs_main_vs_insurance",
            "insurance_rescues": insurance_rescues,
            "reverse_discordant": reverse,
            "p_value": round(mcnemar_p, 8),
            "significant_at_0_05": mcnemar_p < 0.05,
        },
        "priced_subset_analysis": {
            "n": priced["n"],
            "total_stake": round(priced["stake"], 4),
            "gross_return": round(priced["gross"], 4),
            "net_return": round(priced["net"], 4),
            "roi": round(priced["net"] / priced["stake"], 8) if priced["stake"] else None,
            "drawdown": round(max_dd, 4),
            "profit_factor": _profit_factor(priced["wins"], priced["losses"]),
        },
        "calibration_error": {
            "exact3": _cal_error(cal_bins["exact3"]),
            "exact3_main": _cal_error(cal_bins["main"]),
            "exact3_main_insurance": _cal_error(cal_bins["ins"]),
        },
        "main_plus_insurance_outperforms_main": (
            stats["exact3_main_insurance"]["hits"] > stats["exact3_main"]["hits"]
        ),
    }
