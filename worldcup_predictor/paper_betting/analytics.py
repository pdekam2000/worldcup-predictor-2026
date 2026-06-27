"""Paper betting analytics — Phase A18."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.betting_plan.bankroll import recommend_stake
from worldcup_predictor.paper_betting.store import PaperBettingStore, _current_month


def _period_start(period: str) -> str | None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if period == "today":
        return now.strftime("%Y-%m-%d")
    if period == "week":
        start = now - timedelta(days=now.weekday())
        return start.strftime("%Y-%m-%d")
    if period == "month":
        return now.strftime("%Y-%m-01")
    return None


def build_summary(
    store: PaperBettingStore,
    user_id: str,
    *,
    period: str = "all",
) -> dict[str, Any]:
    account = store.get_account(user_id)
    since = _period_start(period) if period != "all" else None
    stats = store.aggregate_stats(user_id, since=since)

    starting = float(account["starting_bankroll"]) if account else 0.0
    current = float(account["current_bankroll"]) if account else starting
    profit = round(current - starting, 2) if account else stats["profit_loss"]
    roi = round((profit / starting) * 100, 2) if starting > 0 else 0.0
    settled = stats["won"] + stats["lost"] + stats["partial"]
    winrate = round((stats["won"] / settled) * 100, 1) if settled > 0 else None
    avg_q = round(sum(stats["qualities"]) / len(stats["qualities"]), 1) if stats["qualities"] else None

    best_market = None
    worst_market = None
    best_rate = -1.0
    worst_rate = 2.0
    for mk, rec in stats["markets"].items():
        total = rec["won"] + rec["lost"]
        if total < 2:
            continue
        rate = rec["won"] / total
        if rate > best_rate:
            best_rate = rate
            best_market = mk
        if rate < worst_rate:
            worst_rate = rate
            worst_market = mk

    best_combo = None
    best_combo_rate = -1.0
    for ct, rec in stats["combo_types"].items():
        total = rec["won"] + rec["lost"]
        if total < 1:
            continue
        rate = rec["won"] / total
        if rate > best_combo_rate:
            best_combo_rate = rate
            best_combo = ct

    return {
        "period": period,
        "starting_bankroll": starting,
        "current_bankroll": current,
        "currency": account.get("currency") if account else "EUR",
        "risk_profile": account.get("risk_profile") if account else "balanced",
        "profit_loss": profit,
        "roi_pct": roi,
        "winrate": winrate,
        "total_bets": stats["total"],
        "pending": stats["pending"],
        "won": stats["won"],
        "lost": stats["lost"],
        "void": stats["void"],
        "partial": stats["partial"],
        "average_quality": avg_q,
        "best_market": best_market,
        "worst_market": worst_market,
        "best_combo_type": best_combo,
    }


def build_strategy_comparison(
    store: PaperBettingStore,
    user_id: str,
    *,
    bankroll: float = 100.0,
) -> dict[str, Any]:
    bets = [
        b for b in store.list_bets(user_id, limit=500)
        if b.get("status") in ("won", "lost", "partial")
    ]
    if len(bets) < 3:
        return {
            "available": False,
            "message": "Not enough settled bets for strategy comparison (need at least 3).",
            "profiles": [],
        }

    profiles_out = []
    for profile in ("conservative", "balanced", "aggressive"):
        virtual_bankroll = float(bankroll)
        peak = virtual_bankroll
        max_drawdown = 0.0
        stakes = []
        qualities = []
        wins = 0
        settled = 0

        for bet in sorted(bets, key=lambda x: x.get("created_at") or ""):
            q = float(bet.get("bet_quality_score") or 50)
            is_combo = bool(bet.get("combo_group_id"))
            rec = recommend_stake(virtual_bankroll, profile=profile, bet_quality_score=q, is_combo=is_combo)
            stake = float(rec["recommended_stake"])
            stakes.append(stake)
            qualities.append(q)
            settled += 1

            status = bet.get("status")
            odds = float(bet["odds_decimal"]) if bet.get("odds_decimal") else None
            if status == "won" and odds and odds > 1:
                virtual_bankroll += stake * (odds - 1)
                wins += 1
            elif status == "lost":
                virtual_bankroll -= stake
            elif status == "partial":
                if odds and odds > 1:
                    virtual_bankroll += stake * 0.5 * (odds - 1)
                wins += 0.5

            peak = max(peak, virtual_bankroll)
            dd = (peak - virtual_bankroll) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, dd)

        profit = round(virtual_bankroll - bankroll, 2)
        roi = round((profit / bankroll) * 100, 2) if bankroll > 0 else 0
        profiles_out.append(
            {
                "profile": profile,
                "profit_loss": profit,
                "roi_pct": roi,
                "winrate": round((wins / settled) * 100, 1) if settled else None,
                "max_drawdown_pct": round(max_drawdown * 100, 1),
                "average_stake": round(sum(stakes) / len(stakes), 2) if stakes else None,
                "average_quality": round(sum(qualities) / len(qualities), 1) if qualities else None,
                "bet_count": settled,
            }
        )

    best = max(profiles_out, key=lambda x: x.get("roi_pct") or -999)
    return {
        "available": True,
        "simulated_bankroll": bankroll,
        "bet_count": len(bets),
        "profiles": profiles_out,
        "best_profile": best.get("profile"),
    }


def build_monthly_report(store: PaperBettingStore, user_id: str, *, month: str | None = None) -> dict[str, Any]:
    m = month or _current_month()
    account = store.get_account(user_id, month=m)
    bets = [b for b in store.list_bets(user_id, limit=500) if str(b.get("created_at", "")).startswith(m)]
    stats = store.aggregate_stats(user_id, since=f"{m}-01")

    starting = float(account["starting_bankroll"]) if account else 100.0
    current = float(account["current_bankroll"]) if account else starting
    profit = round(current - starting, 2)
    roi = round((profit / starting) * 100, 2) if starting > 0 else 0.0
    settled = stats["won"] + stats["lost"] + stats["partial"]
    winrate = round((stats["won"] / settled) * 100, 1) if settled > 0 else None

    tier_won: dict[str, int] = {"elite": 0, "strong": 0, "good": 0, "risky": 0}
    tier_lost: dict[str, int] = {"elite": 0, "strong": 0, "good": 0, "risky": 0}
    for b in bets:
        if b.get("status") not in ("won", "lost"):
            continue
        q = float(b.get("bet_quality_score") or 0)
        tier = "risky"
        if q >= 90:
            tier = "elite"
        elif q >= 80:
            tier = "strong"
        elif q >= 70:
            tier = "good"
        if b["status"] == "won":
            tier_won[tier] += 1
        else:
            tier_lost[tier] += 1

    def _best_tier(won_d, lost_d):
        best = None
        best_rate = -1
        for t in won_d:
            total = won_d[t] + lost_d[t]
            if total < 1:
                continue
            rate = won_d[t] / total
            if rate > best_rate:
                best_rate = rate
                best = t
        return best

    best_tier = _best_tier(tier_won, tier_lost)
    worst_tier = None
    worst_rate = 2.0
    for t in tier_won:
        total = tier_won[t] + tier_lost[t]
        if total < 1:
            continue
        rate = tier_lost[t] / total
        if rate > worst_rate or worst_tier is None:
            worst_rate = rate
            worst_tier = t

    best_combo = None
    best_combo_rate = -1
    for ct, rec in stats["combo_types"].items():
        total = rec["won"] + rec["lost"]
        if total < 1:
            continue
        rate = rec["won"] / total
        if rate > best_combo_rate:
            best_combo_rate = rate
            best_combo = ct

    if profit > 0 and roi > 5:
        next_rec = "Continue current risk profile; focus on elite/strong quality singles."
    elif profit < 0:
        next_rec = "Reduce stake size and favor safe combos only next month."
    else:
        next_rec = "Maintain disciplined virtual stakes; wait for higher-quality days."

    report = {
        "month": m,
        "headline": f"If you followed AI tips with virtual bankroll {starting:.0f} {account.get('currency') if account else 'EUR'}, net result was {profit:+.2f}",
        "starting_bankroll": starting,
        "ending_bankroll": current,
        "net_profit_loss": profit,
        "roi_pct": roi,
        "winrate": winrate,
        "total_bets": len(bets),
        "best_market": build_summary(store, user_id, period="month").get("best_market"),
        "worst_market": build_summary(store, user_id, period="month").get("worst_market"),
        "best_quality_tier": best_tier,
        "worst_quality_tier": worst_tier,
        "best_combo_type": best_combo,
        "recommendation_next_month": next_rec,
        "disclaimer": "Virtual betting is for analysis and education only. It does not guarantee real-money results.",
    }
    store.save_monthly_report(user_id, m, report)
    return report
