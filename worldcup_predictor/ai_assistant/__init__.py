"""AI Watchlist, Smart Alerts & Daily Assistant — Phase A19."""

from worldcup_predictor.ai_assistant.service import (
    add_watchlist_item,
    get_daily_briefing,
    get_preferences,
    get_weekly_insights,
    list_notifications,
    list_watchlist,
    mark_all_notifications_read,
    mark_notification_read,
    remove_watchlist_item,
    run_alert_scan,
    update_preferences,
)

__all__ = [
    "add_watchlist_item",
    "get_daily_briefing",
    "get_preferences",
    "get_weekly_insights",
    "list_notifications",
    "list_watchlist",
    "mark_all_notifications_read",
    "mark_notification_read",
    "remove_watchlist_item",
    "run_alert_scan",
    "update_preferences",
]
