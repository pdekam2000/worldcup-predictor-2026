"""Historical always-bet vs portfolio-managed validation (research-only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.correlation import analyze_diversification
from worldcup_predictor.research.bet_portfolio_manager.daily_score import compute_daily_portfolio_score
from worldcup_predictor.research.bet_portfolio_manager.fixture_ranking import rank_fixtures
from worldcup_predictor.research.bet_portfolio_manager.input_adapter import attach_outcomes, normalize_fixture
from worldcup_predictor.research.bet_portfolio_manager.no_bet import decide_no_bet


def _league_reliability(fixtures: list[dict[str, Any]]) -> dict[str, float]:
    by: dict[str, list[int]] = defaultdict(list)
    for fx in fixtures:
        n = attach_outcomes(normalize_fixture(fx))
        if n.get("hit_insurance") is None:
            continue
        by[str(n.get("league") or "unknown")].append(1 if n["hit_insurance"] else 0)
    out = {}
    for lg, hits in by.items():
        out[lg] = (sum(hits) / len(hits)) if hits else 0.55
    return out


def _day_key(fx: dict[str, Any], idx: int) -> str:
    k = str(fx.get("kickoff") or "")[:10]
    if len(k) >= 10:
        return k
    # Synthetic day buckets of 3 for corpora without kickoff dates
    return f"bucket_{(idx // 3):05d}"


def run_historical_portfolio_validation(
    fixtures: list[dict[str, Any]],
    *,
    bankroll: float = 1000.0,
    mode: str = "score_weighted",
) -> dict[str, Any]:
    """
    Compare Always-Bet (all fixtures unit stake) vs Portfolio-Managed days.
    Uses Main+Insurance hit as coupon survival proxy when actual_score present.
    """
    lr = _league_reliability(fixtures)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i, raw in enumerate(fixtures):
        fx = attach_outcomes(normalize_fixture(raw))
        by_day[_day_key(raw, i)].append(fx)

    always = {
        "n_days": 0,
        "staked": 0.0,
        "net": 0.0,
        "wins": 0,
        "losses": 0,
        "equity": [],
        "exposures": [],
    }
    managed = {
        "n_days": 0,
        "staked": 0.0,
        "net": 0.0,
        "wins": 0,
        "losses": 0,
        "skipped": 0,
        "equity": [],
        "exposures": [],
        "grades": defaultdict(int),
        "actions": defaultdict(int),
    }
    eq_a = 0.0
    eq_m = 0.0
    peak_a = 0.0
    peak_m = 0.0
    dd_a = 0.0
    dd_m = 0.0

    for day, rows in sorted(by_day.items()):
        # Always bet: unit 1 per fixture
        always["n_days"] += 1
        day_stake_a = float(len(rows))
        always["staked"] += day_stake_a
        always["exposures"].append(day_stake_a)
        day_pnl_a = 0.0
        for fx in rows:
            if fx.get("hit_insurance") is True:
                odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
                day_pnl_a += odd - 1.0
                always["wins"] += 1
            elif fx.get("hit_insurance") is False:
                day_pnl_a -= 1.0
                always["losses"] += 1
        always["net"] += day_pnl_a
        eq_a += day_pnl_a
        peak_a = max(peak_a, eq_a)
        dd_a = max(dd_a, peak_a - eq_a)
        always["equity"].append(round(eq_a, 4))

        # Portfolio managed
        daily = compute_daily_portfolio_score(rows, league_reliability=lr)
        ranking = rank_fixtures(rows, league_reliability=lr)
        div = analyze_diversification(rows)
        decision = decide_no_bet(daily, ranking, div)
        managed["grades"][str(daily.get("grade"))] += 1
        managed["actions"][str(decision.get("action"))] += 1
        managed["n_days"] += 1

        if decision.get("skip_day"):
            managed["skipped"] += 1
            managed["exposures"].append(0.0)
            managed["equity"].append(round(eq_m, 4))
            continue

        # Unit-stake comparison on selected fixtures (fair vs always-bet unit stake)
        selected_ids = set(int(x) for x in (decision.get("selected_fixture_ids") or []))
        selected_rows = [fx for fx in rows if int(fx["fixture_id"]) in selected_ids]
        day_stake_m = float(len(selected_rows))
        managed["staked"] += day_stake_m
        managed["exposures"].append(day_stake_m)
        day_pnl_m = 0.0
        for fx in selected_rows:
            if fx.get("hit_insurance") is True:
                odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
                day_pnl_m += odd - 1.0
                managed["wins"] += 1
            elif fx.get("hit_insurance") is False:
                day_pnl_m -= 1.0
                managed["losses"] += 1
        managed["net"] += day_pnl_m
        eq_m += day_pnl_m
        peak_m = max(peak_m, eq_m)
        dd_m = max(dd_m, peak_m - eq_m)
        managed["equity"].append(round(eq_m, 4))

    def _pack(block: dict[str, Any], *, skipped: int | None = None) -> dict[str, Any]:
        staked = float(block["staked"]) or 1e-9
        return {
            "n_days": block["n_days"],
            "total_staked": round(float(block["staked"]), 4),
            "net_return": round(float(block["net"]), 4),
            "roi": round(float(block["net"]) / staked, 8),
            "wins": block["wins"],
            "losses": block["losses"],
            "win_frequency": round(
                block["wins"] / max(1, block["wins"] + block["losses"]), 8
            ),
            "average_exposure": round(
                sum(block["exposures"]) / max(1, len(block["exposures"])), 4
            ),
            "skipped_days": skipped,
        }

    always_pack = _pack(always)
    always_pack["max_drawdown"] = round(dd_a, 4)
    managed_pack = _pack(managed, skipped=managed["skipped"])
    managed_pack["max_drawdown"] = round(dd_m, 4)
    managed_pack["grade_distribution"] = dict(managed["grades"])
    managed_pack["action_distribution"] = dict(managed["actions"])
    managed_pack["skip_rate"] = round(managed["skipped"] / max(1, managed["n_days"]), 8)

    capital_efficiency_always = always_pack["roi"]
    capital_efficiency_managed = managed_pack["roi"]

    return {
        "research_only": True,
        "bankroll_eur": bankroll,
        "allocation_mode": mode,
        "n_fixtures": len(fixtures),
        "n_days": len(by_day),
        "always_bet": always_pack,
        "portfolio_managed": managed_pack,
        "improvement": {
            "roi_delta": round(managed_pack["roi"] - always_pack["roi"], 8),
            "drawdown_delta": round(always_pack["max_drawdown"] - managed_pack["max_drawdown"], 4),
            "drawdown_improved": managed_pack["max_drawdown"] <= always_pack["max_drawdown"],
            "capital_efficiency_delta": round(capital_efficiency_managed - capital_efficiency_always, 8),
            "average_skipped_bad_days": managed["skipped"],
            "skip_rate": managed_pack["skip_rate"],
        },
        "note": (
            "Primary PnL comparison uses unit stakes on selected fixtures vs unit stakes on all fixtures. "
            "Bankroll-scaled allocation is reported separately by the capital allocator (not in this PnL path)."
        ),
        "league_reliability_used": lr,
    }
