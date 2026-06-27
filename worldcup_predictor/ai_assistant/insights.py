"""Weekly performance insights — Phase A19."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.ai_assistant.store import AssistantStore
from worldcup_predictor.paper_betting.store import PaperBettingStore


def build_weekly_insights(user_id: str, *, store: AssistantStore | None = None) -> dict[str, Any]:
    store = store or AssistantStore()
    pb = PaperBettingStore()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).replace(tzinfo=None).isoformat()

    bets = [
        b for b in pb.list_bets(user_id, limit=500)
        if str(b.get("created_at", "")) >= week_ago
    ]
    settled = [b for b in bets if b.get("status") in ("won", "lost", "partial")]
    won = sum(1 for b in settled if b.get("status") == "won")

    qualities = [float(b["bet_quality_score"]) for b in bets if b.get("bet_quality_score")]
    avg_quality = round(sum(qualities) / len(qualities), 1) if qualities else None

    markets: dict[str, dict[str, int]] = {}
    for b in settled:
        mk = str(b.get("market") or "unknown")
        markets.setdefault(mk, {"won": 0, "lost": 0})
        if b.get("status") == "won":
            markets[mk]["won"] += 1
        elif b.get("status") == "lost":
            markets[mk]["lost"] += 1

    best_market = None
    worst_market = None
    best_rate = -1.0
    worst_rate = 2.0
    for mk, rec in markets.items():
        total = rec["won"] + rec["lost"]
        if total < 1:
            continue
        rate = rec["won"] / total
        if rate > best_rate:
            best_rate = rate
            best_market = mk
        if rate < worst_rate:
            worst_rate = rate
            worst_market = mk

    combo_types: dict[str, dict[str, int]] = {}
    for b in settled:
        if not b.get("combo_group_id"):
            continue
        ct = str(b.get("combo_type") or "combo")
        combo_types.setdefault(ct, {"won": 0, "lost": 0})
        if b.get("status") == "won":
            combo_types[ct]["won"] += 1
        elif b.get("status") == "lost":
            combo_types[ct]["lost"] += 1

    profit_week = sum(float(b.get("profit_loss") or 0) for b in settled if b.get("profit_loss") is not None)

    return {
        "period": "week",
        "available": len(settled) >= 1,
        "message": None if settled else "Not enough settled bets for weekly insights.",
        "roi_trend": profit_week,
        "winrate_trend": round((won / len(settled)) * 100, 1) if settled else None,
        "best_market": best_market,
        "worst_market": worst_market,
        "average_quality": avg_quality,
        "combo_performance": combo_types,
        "settled_bets": len(settled),
        "total_bets": len(bets),
    }
