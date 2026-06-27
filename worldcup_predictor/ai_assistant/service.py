"""AI Assistant service layer — Phase A19."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.ai_assistant.briefing import build_daily_briefing
from worldcup_predictor.ai_assistant.channels import deliver_notification
from worldcup_predictor.ai_assistant.constants import WATCHLIST_TYPES
from worldcup_predictor.ai_assistant.insights import build_weekly_insights
from worldcup_predictor.ai_assistant.scheduler import run_alert_scan
from worldcup_predictor.ai_assistant.store import AssistantStore


def list_watchlist(user_id: str) -> dict[str, Any]:
    store = AssistantStore()
    return {"status": "ok", "watchlist": store.list_watchlist(user_id)}


def add_watchlist_item(
    user_id: str,
    *,
    item_type: str,
    item_id: str,
    item_name: str | None = None,
    item_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if item_type not in WATCHLIST_TYPES:
        return {"status": "error", "message": f"Invalid item_type. Use one of: {WATCHLIST_TYPES}"}
    store = AssistantStore()
    item = store.add_watchlist(
        user_id,
        item_type=item_type,
        item_id=item_id,
        item_name=item_name,
        item_meta=item_meta,
    )
    return {"status": "ok", "item": item}


def remove_watchlist_item(user_id: str, watchlist_id: int) -> dict[str, Any]:
    store = AssistantStore()
    if not store.remove_watchlist(user_id, watchlist_id):
        return {"status": "error", "message": "Watchlist item not found"}
    return {"status": "ok"}


def get_preferences(user_id: str) -> dict[str, Any]:
    store = AssistantStore()
    return {"status": "ok", "preferences": store.get_preferences(user_id)}


def update_preferences(user_id: str, prefs: dict[str, Any]) -> dict[str, Any]:
    store = AssistantStore()
    updated = store.upsert_preferences(user_id, prefs)
    return {"status": "ok", "preferences": updated}


def list_notifications(
    user_id: str,
    *,
    category: str | None = None,
) -> dict[str, Any]:
    store = AssistantStore()
    items = store.list_notifications(user_id, category=category)
    unread = store.unread_count(user_id)
    return {"status": "ok", "notifications": items, "unread_count": unread}


def mark_notification_read(user_id: str, notification_id: int) -> dict[str, Any]:
    store = AssistantStore()
    if not store.mark_read(user_id, notification_id):
        return {"status": "error", "message": "Notification not found"}
    return {"status": "ok"}


def mark_all_notifications_read(user_id: str) -> dict[str, Any]:
    store = AssistantStore()
    count = store.mark_all_read(user_id)
    return {"status": "ok", "updated": count}


def get_daily_briefing(user_id: str, *, plan_date: str | None = None) -> dict[str, Any]:
    briefing = build_daily_briefing(user_id, plan_date=plan_date)
    return {"status": "ok", "briefing": briefing}


def get_weekly_insights(user_id: str) -> dict[str, Any]:
    insights = build_weekly_insights(user_id)
    return {"status": "ok", "insights": insights}


def create_assistant_notification(
    user_id: str,
    *,
    category: str,
    alert_type: str,
    title: str,
    message: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    store = AssistantStore()
    prefs = store.get_preferences(user_id)
    n = store.create_notification(
        user_id,
        category=category,
        alert_type=alert_type,
        title=title,
        message=message,
        fixture_id=kwargs.get("fixture_id"),
        old_value=kwargs.get("old_value"),
        new_value=kwargs.get("new_value"),
        reason=kwargs.get("reason"),
        link=kwargs.get("link"),
        dedup_key=kwargs.get("dedup_key"),
    )
    if n:
        deliver_notification(user_id, n, enabled_channels=prefs.get("channels"))
    return n
