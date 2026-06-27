"""Daily AI Briefing — Phase A19."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.ai_assistant.store import AssistantStore
from worldcup_predictor.betting_plan.engine import build_daily_betting_plan
from worldcup_predictor.paper_betting.analytics import build_summary
from worldcup_predictor.paper_betting.store import PaperBettingStore


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_daily_briefing(
    user_id: str,
    *,
    plan_date: str | None = None,
    store: AssistantStore | None = None,
) -> dict[str, Any]:
    store = store or AssistantStore()
    day = plan_date or _utc_today()
    watchlist = store.list_watchlist(user_id)
    prefs = store.get_preferences(user_id)

    plan = build_daily_betting_plan(plan_date=day, include_tomorrow=False)
    singles = plan.get("best_single_bets") or []
    combos = plan.get("combos") or {}
    avoid = plan.get("avoid") or []
    day_quality = plan.get("day_quality") or {}

    # Filter to watched items when watchlist non-empty
    if watchlist:
        watched_fixtures = {
            int(i["item_id"])
            for i in watchlist
            if i.get("item_type") == "fixture"
        }
        watched_comps = {
            str(i["item_id"]).lower()
            for i in watchlist
            if i.get("item_type") == "competition"
        }
        watched_teams = {
            str(i["item_id"]).lower()
            for i in watchlist
            if i.get("item_type") == "team"
        }

        def _watched(leg: dict[str, Any]) -> bool:
            fid = int(leg.get("fixture_id") or 0)
            if fid in watched_fixtures:
                return True
            ck = str(leg.get("competition_key") or "").lower()
            if ck and ck in watched_comps:
                return True
            ht = str(leg.get("home_team") or "").lower()
            at = str(leg.get("away_team") or "").lower()
            return ht in watched_teams or at in watched_teams

        singles = [s for s in singles if _watched(s)]
        avoid = [a for a in avoid if _watched(a)]

    min_q = float(prefs.get("min_bet_quality") or 0)
    singles = [s for s in singles if float(s.get("bet_quality_score") or 0) >= min_q]

    best_combos = []
    for key in ("safe", "balanced", "value"):
        combo = combos.get(key)
        if combo and combo.get("legs"):
            best_combos.append(combo)

    highest_quality = sorted(
        singles,
        key=lambda x: float(x.get("bet_quality_score") or 0),
        reverse=True,
    )[:5]

    # Overnight quality changes from notifications
    overnight = [
        n for n in store.list_notifications(user_id, category="quality", limit=20)
        if str(n.get("created_at", "")).startswith(day)
    ]

    # Paper betting
    pb_store = PaperBettingStore()
    paper_summary = build_summary(pb_store, user_id, period="month")

    # Archive accuracy snippet (read-only aggregate)
    archive_update = _archive_accuracy_snippet()

    lineup_news = [
        n for n in store.list_notifications(user_id, category="prediction", limit=10)
        if n.get("alert_type") == "lineup_published" and str(n.get("created_at", "")).startswith(day)
    ]

    return {
        "date": day,
        "headline": f"Daily briefing for {day}",
        "day_quality": day_quality,
        "best_singles": singles[:8],
        "best_combos": best_combos[:3],
        "matches_to_avoid": avoid[:5],
        "highest_quality_fixtures": highest_quality,
        "lineup_news": lineup_news,
        "quality_changes_overnight": overnight,
        "paper_betting": {
            "profit_loss": paper_summary.get("profit_loss"),
            "roi_pct": paper_summary.get("roi_pct"),
            "winrate": paper_summary.get("winrate"),
            "pending": paper_summary.get("pending"),
        },
        "archive_accuracy": archive_update,
        "watchlist_count": len(watchlist),
        "disclaimer": "AI briefing is for analysis and education only. It does not guarantee real-money results.",
    }


def _archive_accuracy_snippet() -> dict[str, Any]:
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        row = repo._conn.execute(  # noqa: SLF001
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN market_1x2_status = 'correct' THEN 1 ELSE 0 END) AS correct
            FROM worldcup_prediction_evaluations
            WHERE market_1x2_status IN ('correct', 'wrong')
            """,
        ).fetchone()
        if not row or not row[0]:
            return {"available": False}
        total = int(row[0])
        correct = int(row[1] or 0)
        return {
            "available": True,
            "settled": total,
            "accuracy_pct": round((correct / total) * 100, 1) if total else None,
        }
    except Exception:
        return {"available": False}
