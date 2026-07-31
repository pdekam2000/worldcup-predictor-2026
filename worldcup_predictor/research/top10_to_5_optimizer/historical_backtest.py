"""Historical backtest — priced monetary vs unpriced probability-mass separated."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer.coupon_generator import generate_coupon_universe
from worldcup_predictor.research.top10_to_5_optimizer.market_semantics import settles_as_win
from worldcup_predictor.research.top10_to_5_optimizer.constants import WIN, PUSH


def _hit(scores: list[str], actual: str) -> bool:
    a = str(actual).replace(" ", "")
    return a in {str(s).replace(" ", "") for s in scores}


def _roi(net: float, stake: float) -> float | None:
    if stake <= 1e-12:
        return None
    return round(net / stake, 8)


def _equity_dd(pnls: list[float]) -> float:
    eq = peak = dd = 0.0
    streak = best = 0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        if p < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return dd


def simulate_layer_pnl(
    *,
    actual: str,
    exact3: list[str],
    main_market: dict[str, Any] | None,
    insurance_market: dict[str, Any] | None,
    stakes: dict[str, float],
    exact_odds: dict[str, float | None],
) -> dict[str, Any]:
    parts = str(actual).replace(" ", "").split("-")
    if len(parts) != 2:
        return {"net": None, "priced": False}
    hg, ag = int(parts[0]), int(parts[1])
    missing = False
    gross = 0.0
    stake_total = 0.0

    def add_exact(i: int, sc: str) -> None:
        nonlocal gross, stake_total, missing
        key = f"exact_{i}"
        st = float(stakes.get(key) or 0)
        stake_total += st
        odd = exact_odds.get(sc)
        won = settles_as_win("exact_score", {"score": sc}, hg, ag) == WIN
        if won:
            if odd is None or float(odd) <= 1:
                missing = True
            else:
                gross += st * float(odd)

    for i, sc in enumerate(exact3[:3], start=1):
        add_exact(i, sc)

    def add_mkt(key: str, m: dict[str, Any] | None) -> None:
        nonlocal gross, stake_total, missing
        if not m:
            return
        st = float(stakes.get(key) or 0)
        stake_total += st
        out = settles_as_win(m["market_type"], m.get("market_parameters") or {}, hg, ag)
        if out == PUSH:
            gross += st
            return
        if out == WIN:
            odd = m.get("decimal_odds")
            if odd is None or float(odd) <= 1:
                missing = True
            else:
                gross += st * float(odd)

    add_mkt("market_1", main_market)
    add_mkt("market_2", insurance_market)
    if missing:
        return {"net": None, "priced": False, "stake": stake_total, "gross": None}
    net = gross - stake_total
    return {"net": round(net, 8), "priced": True, "stake": stake_total, "gross": round(gross, 8)}


def run_historical_backtest(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Each fixture dict expects:
      fixture_id, actual_score, top10, exact3, recommendation (optional),
      main_market, insurance_market, markets (optional), stakes, exact_odds,
      layers for comparison may include bco-style main_coverage_scores
    """
    strategies = {
        "exact3_only": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
        "exact3_main": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
        "exact3_main_insurance": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
        "top10_to_5": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
        "optimized_25": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
        "optimized_64": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
        "full_125": {"priced": [], "unpriced_mass": [], "hits": 0, "n": 0, "nets": [], "stakes": []},
    }
    excluded = []
    source_cmp = {
        "canonical": {"hits": 0, "n": 0, "profitable_mass_sum": 0.0, "full_loss_sum": 0.0},
        "exact_v2": {"hits": 0, "n": 0, "profitable_mass_sum": 0.0, "full_loss_sum": 0.0},
        "consensus": {"hits": 0, "n": 0, "profitable_mass_sum": 0.0, "full_loss_sum": 0.0},
    }

    for fx in fixtures:
        actual = fx.get("actual_score")
        if not actual:
            excluded.append({"fixture_id": fx.get("fixture_id"), "reason": "missing_actual"})
            continue
        exact3 = list(fx.get("exact3") or [])
        stakes = dict(fx.get("stakes") or {})
        exact_odds = dict(fx.get("exact_odds") or {})
        main = fx.get("main_market")
        ins = fx.get("insurance_market")
        top10 = list(fx.get("top10") or [])

        # Hit rates / mass
        for key, scores, mkt1, mkt2 in (
            ("exact3_only", exact3, None, None),
            ("exact3_main", exact3, main, None),
            ("exact3_main_insurance", exact3, main, ins),
            ("top10_to_5", exact3, main, ins),
        ):
            strategies[key]["n"] += 1
            if _hit(exact3 if key == "exact3_only" else exact3, actual):
                # For coverage layers, also count market wins as "raw hit" via pnl path
                pass
            if key == "exact3_only" and _hit(exact3, actual):
                strategies[key]["hits"] += 1
            elif key != "exact3_only":
                # raw outcome: exact hit OR market covers actual
                covered = _hit(exact3, actual)
                for m in (mkt1, mkt2):
                    if not m:
                        continue
                    parts = str(actual).replace(" ", "").split("-")
                    if len(parts) == 2:
                        o = settles_as_win(m["market_type"], m.get("market_parameters") or {}, int(parts[0]), int(parts[1]))
                        if o in {WIN, PUSH}:
                            covered = True
                if covered:
                    strategies[key]["hits"] += 1

            pnl = simulate_layer_pnl(
                actual=str(actual),
                exact3=exact3,
                main_market=mkt1,
                insurance_market=mkt2,
                stakes=stakes
                if key != "exact3_only"
                else {k: stakes.get(k, 0) for k in ("exact_1", "exact_2", "exact_3")},
                exact_odds=exact_odds,
            )
            if pnl.get("priced"):
                strategies[key]["priced"].append(pnl)
                strategies[key]["nets"].append(float(pnl["net"]))
                strategies[key]["stakes"].append(float(pnl["stake"]))
            else:
                strategies[key]["unpriced_mass"].append(fx.get("fixture_id"))

        # Coupon strategies when three-fixture groups provided
        if fx.get("coupon_group"):
            continue

        # Source comparison hooks
        src = str(fx.get("top10_source") or "consensus")
        if src in source_cmp:
            source_cmp[src]["n"] += 1
            tops = [str(r.get("scoreline") or r.get("score")) for r in top10]
            if _hit(tops, str(actual)):
                source_cmp[src]["hits"] += 1
            source_cmp[src]["profitable_mass_sum"] += float(fx.get("profitable_mass") or 0)
            source_cmp[src]["full_loss_sum"] += float(fx.get("full_loss_mass") or 0)

    # Optional coupon groups
    for group in [fx for fx in fixtures if fx.get("is_coupon_group")]:
        for cap, key in ((25, "optimized_25"), (64, "optimized_64"), (125, "full_125")):
            uni = generate_coupon_universe(group["fixture_selections"], ticket_cap=cap)
            strategies[key]["n"] += 1
            # Mass utility as unpriced proxy when not fully priced
            if uni.get("expected_coupon_value") is not None:
                strategies[key]["priced"].append(
                    {"net": float(uni["expected_coupon_value"]), "stake": float(group.get("total_stake") or 1.0)}
                )
                strategies[key]["nets"].append(float(uni["expected_coupon_value"]))
                strategies[key]["stakes"].append(float(group.get("total_stake") or 1.0))
            else:
                strategies[key]["unpriced_mass"].append(uni.get("probability_mass_utility"))

    def summarize(s: dict[str, Any]) -> dict[str, Any]:
        nets = s["nets"]
        stakes = s["stakes"]
        st = sum(stakes)
        net = sum(nets)
        return {
            "n": s["n"],
            "hit_rate": round(s["hits"] / s["n"], 8) if s["n"] else None,
            "priced_count": len(s["priced"]),
            "unpriced_count": len(s["unpriced_mass"]),
            "priced_monetary": {
                "net_return": round(net, 8) if s["priced"] else None,
                "gross_return": None,
                "roi": _roi(net, st) if s["priced"] else None,
                "max_drawdown": round(_equity_dd(nets), 8) if nets else None,
                "profit_factor": None,
                "capital_efficiency": _roi(net, st) if s["priced"] else None,
            },
            "unpriced_probability_mass_analysis": {
                "note": "separated from monetary — no mixing",
                "entries": len(s["unpriced_mass"]),
            },
        }

    out_strategies = {k: summarize(v) for k, v in strategies.items()}
    # Family of best pairs from fixture meta
    families: dict[str, int] = {}
    for fx in fixtures:
        for lab in fx.get("selected_pair_families") or []:
            families[str(lab)] = families.get(str(lab), 0) + 1

    return {
        "research_only": True,
        "not_deployed": True,
        "historical_fixture_count": sum(1 for fx in fixtures if not fx.get("is_coupon_group")),
        "excluded": excluded,
        "strategies": out_strategies,
        "model_source_comparison": {
            k: {
                "top10_hit_rate": round(v["hits"] / v["n"], 8) if v["n"] else None,
                "n": v["n"],
                "avg_profitable_mass": round(v["profitable_mass_sum"] / v["n"], 8) if v["n"] else None,
                "avg_full_loss_mass": round(v["full_loss_sum"] / v["n"], 8) if v["n"] else None,
                "exact_v2_promoted": False,
            }
            for k, v in source_cmp.items()
        },
        "best_market_pair_families": sorted(families.items(), key=lambda x: -x[1])[:10],
        "separation_enforced": {
            "priced_monetary_analysis": True,
            "unpriced_probability_mass_analysis": True,
            "mixed": False,
        },
    }
