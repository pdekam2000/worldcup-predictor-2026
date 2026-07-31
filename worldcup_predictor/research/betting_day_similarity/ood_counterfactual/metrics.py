"""Counterfactual metrics helpers — research-only."""

from __future__ import annotations

from typing import Any


def summarize_policy_rows(rows: list[dict[str, Any]], exposure_key: str, pnl_key: str) -> dict[str, Any]:
    n = len(rows) or 1
    staked = sum(float(r.get(exposure_key) or 0) for r in rows)
    pnl = sum(float(r.get(pnl_key) or 0) for r in rows)
    active = [r for r in rows if float(r.get(exposure_key) or 0) > 0]
    wins = sum(1 for r in rows if float(r.get(pnl_key) or 0) > 0)
    losses = sum(1 for r in rows if float(r.get(pnl_key) or 0) < 0)
    eq = peak = dd = 0.0
    streak = best_streak = 0
    survivals = []
    fails = []
    rescues = []
    for r in rows:
        p = float(r.get(pnl_key) or 0)
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        if p < 0:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0
        if r.get("coupon_survival") is not None:
            survivals.append(float(r["coupon_survival"]))
        if r.get("complete_coupon_failure") is not None:
            fails.append(float(r["complete_coupon_failure"]))
        if r.get("insurance_rescue_count") is not None:
            rescues.append(float(r["insurance_rescue_count"]))
    avg_stake = (staked / len(active)) if active else 0.0
    return {
        "n_days": len(rows),
        "roi": round(pnl / staked, 8) if staked > 1e-12 else None,
        "net_profit": round(pnl, 6),
        "gross_return": round(pnl + staked, 6) if staked else round(pnl, 6),
        "max_drawdown": round(dd, 6),
        "average_exposure": round(staked / n, 6),
        "capital_efficiency": round(pnl / staked, 8) if staked > 1e-12 else None,
        "coupon_survival": round(sum(survivals) / len(survivals), 8) if survivals else None,
        "complete_coupon_failure": round(sum(fails) / len(fails), 8) if fails else None,
        "insurance_rescue": round(sum(rescues) / len(rescues), 8) if rescues else None,
        "winning_days": wins,
        "losing_days": losses,
        "maximum_daily_loss": round(min((float(r.get(pnl_key) or 0) for r in rows), default=0.0), 6),
        "longest_losing_streak": best_streak,
        "average_stake": round(avg_stake, 6),
        "average_capital": round(staked / n, 6),
        "active_day_ratio": round(len(active) / n, 8),
        "total_staked": round(staked, 6),
    }


def delta_table(original: dict[str, Any], counterfactual: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "roi",
        "net_profit",
        "gross_return",
        "max_drawdown",
        "average_exposure",
        "capital_efficiency",
        "coupon_survival",
        "complete_coupon_failure",
        "insurance_rescue",
        "winning_days",
        "losing_days",
        "maximum_daily_loss",
        "longest_losing_streak",
        "average_stake",
        "average_capital",
        "active_day_ratio",
    ]
    out = {}
    for k in keys:
        a = original.get(k)
        b = counterfactual.get(k)
        if a is None or b is None:
            out[k] = {"original": a, "counterfactual": b, "delta": None}
        else:
            out[k] = {
                "original": a,
                "counterfactual": b,
                "delta": round(float(b) - float(a), 8),
            }
    return out


def fixture_outcome_counts(day: dict[str, Any], selected_ids: list[int]) -> dict[str, int]:
    by_id = {int(f["fixture_id"]): f for f in (day.get("fixtures") or [])}
    profit = lose = 0
    for fid in selected_ids:
        fx = by_id.get(int(fid))
        if not fx:
            continue
        if fx.get("hit_insurance") is True:
            profit += 1
        elif fx.get("hit_insurance") is False:
            lose += 1
    return {"profitable_fixtures": profit, "losing_fixtures": lose}
