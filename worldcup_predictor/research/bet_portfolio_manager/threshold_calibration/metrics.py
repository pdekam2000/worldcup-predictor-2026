"""Aggregate metrics for a list of replayed days (research-only)."""

from __future__ import annotations

from typing import Any


def summarize_days(days: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(days) or 1
    staked = sum(float(d.get("exposure_units") or 0) for d in days)
    pnl = sum(float(d.get("realized_pnl_evaluation_only") or 0) for d in days)
    wins = sum(int(d.get("realized_wins") or 0) for d in days)
    losses = sum(int(d.get("realized_losses") or 0) for d in days)
    active = [d for d in days if float(d.get("exposure_units") or 0) > 0]
    zero = [d for d in days if float(d.get("exposure_units") or 0) <= 0]
    # equity curve for drawdown
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for d in days:
        eq += float(d.get("realized_pnl_evaluation_only") or 0)
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    exposures = [float(d.get("exposure_units") or 0) for d in days]
    actions: dict[str, int] = {}
    grades: dict[str, int] = {}
    for d in days:
        a = str(d.get("action") or "UNKNOWN")
        actions[a] = actions.get(a, 0) + 1
        g = str(d.get("grade") or "?")
        grades[g] = grades.get(g, 0) + 1
    return {
        "n_days": len(days),
        "n_active_days": len(active),
        "n_zero_capital_days": len(zero),
        "active_day_ratio": round(len(active) / n, 8),
        "zero_capital_day_ratio": round(len(zero) / n, 8),
        "total_staked": round(staked, 6),
        "net_return": round(pnl, 6),
        "gross_return": round(pnl + staked, 6) if staked else round(pnl, 6),
        "roi": round(pnl / staked, 8) if staked > 1e-12 else None,
        "max_drawdown": round(dd, 6),
        "average_exposure": round(sum(exposures) / n, 6),
        "win_frequency": round(wins / max(1, wins + losses), 8),
        "wins": wins,
        "losses": losses,
        "action_distribution": actions,
        "grade_distribution": grades,
        "avg_score": round(sum(float(d.get("score") or 0) for d in days) / n, 4),
        "avg_fixtures_funded": round(
            sum(len(d.get("selected_fixture_ids") or []) for d in days) / n, 4
        ),
        "max_daily_loss": round(
            min((float(d.get("realized_pnl_evaluation_only") or 0) for d in days), default=0.0), 6
        ),
    }


def always_bet_metrics(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Unit stake on every fixture every day (Always Bet baseline)."""
    synthetic = []
    for d in days:
        pnl = 0.0
        wins = losses = 0
        exposure = 0.0
        for fx in d.get("fixtures") or []:
            exposure += 1.0
            if fx.get("hit_insurance") is True:
                odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
                pnl += odd - 1.0
                wins += 1
            elif fx.get("hit_insurance") is False:
                pnl -= 1.0
                losses += 1
        synthetic.append(
            {
                **d,
                "action": "ALWAYS_BET",
                "exposure_units": exposure,
                "realized_pnl_evaluation_only": pnl,
                "realized_wins": wins,
                "realized_losses": losses,
                "selected_fixture_ids": [int(f["fixture_id"]) for f in (d.get("fixtures") or [])],
            }
        )
    return summarize_days(synthetic)
