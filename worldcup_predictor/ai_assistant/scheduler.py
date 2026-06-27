"""Alert scan scheduler — Phase A19."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.ai_assistant.detectors import (
    detect_combo_alerts,
    detect_paper_betting_alerts,
    scan_user_fixtures,
)
from worldcup_predictor.ai_assistant.store import AssistantStore
from worldcup_predictor.betting_plan.engine import build_daily_betting_plan
from worldcup_predictor.predops.store import PredOpsStore


def run_alert_scan(*, user_id: str | None = None) -> dict[str, Any]:
    store = AssistantStore()
    predops = PredOpsStore()
    user_ids = [user_id] if user_id else store.users_with_watchlist()
    if not user_ids:
        return {"status": "ok", "users_scanned": 0, "notifications_created": 0}

    total_created = 0
    per_user: dict[str, int] = {}

    for uid in user_ids:
        watchlist = store.list_watchlist(uid)
        if not watchlist:
            continue
        prefs = store.get_preferences(uid)
        created = scan_user_fixtures(store, predops, uid, watchlist, prefs)

        # Combo alerts from today's plan
        plan = build_daily_betting_plan(include_tomorrow=False)
        combos = plan.get("combos") or {}
        combo_list = [v for v in combos.values() if isinstance(v, dict)]
        created.extend(detect_combo_alerts(store, uid, combos=combo_list, prefs=prefs))

        # Paper betting settlement alerts
        try:
            from worldcup_predictor.paper_betting.settlement import settle_pending_bets

            settlement = settle_pending_bets(user_id=uid)
            created.extend(
                detect_paper_betting_alerts(store, uid, settlement_result=settlement, prefs=prefs)
            )
        except Exception:
            pass

        per_user[uid] = len(created)
        total_created += len(created)

    return {
        "status": "ok",
        "users_scanned": len(user_ids),
        "notifications_created": total_created,
        "per_user": per_user,
    }
