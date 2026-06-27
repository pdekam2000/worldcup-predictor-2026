"""AI Watchlist, Smart Alerts & Daily Assistant APIs — Phase A19."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from worldcup_predictor.ai_assistant.constants import NOTIFICATION_CATEGORIES, WATCHLIST_TYPES
from worldcup_predictor.ai_assistant.scan_job import run_alert_scan_job
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
    update_preferences,
)
from worldcup_predictor.ai_assistant.store import AssistantStore
from worldcup_predictor.api.deps import get_current_user, require_admin_user
from worldcup_predictor.api.web_auth import WebAuthUser

router = APIRouter(tags=["ai-assistant"])

WatchlistType = Literal["competition", "team", "player", "fixture", "market"]
NotificationCategory = Literal[
    "prediction", "quality", "combo", "paper_betting", "system", "archive"
]


class WatchlistBody(BaseModel):
    item_type: WatchlistType
    item_id: str = Field(..., min_length=1, max_length=128)
    item_name: str | None = Field(default=None, max_length=256)
    item_meta: dict[str, Any] | None = None


class PreferencesBody(BaseModel):
    alert_frequency: str | None = None
    favorite_leagues: list[str] | None = None
    favorite_teams: list[str] | None = None
    min_bet_quality: float | None = Field(default=None, ge=0, le=100)
    min_combo_type: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None
    channels: list[str] | None = None


@router.get("/watchlist")
def api_watchlist_get(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return list_watchlist(user.id)


@router.post("/watchlist")
def api_watchlist_add(
    body: WatchlistBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = add_watchlist_item(
        user.id,
        item_type=body.item_type,
        item_id=body.item_id,
        item_name=body.item_name,
        item_meta=body.item_meta,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result)
    return result


@router.delete("/watchlist/{watchlist_id}")
def api_watchlist_delete(
    watchlist_id: int,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = remove_watchlist_item(user.id, watchlist_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.get("/assistant/notifications")
def api_assistant_notifications(
    category: NotificationCategory | None = Query(default=None),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return list_notifications(user.id, category=category)


@router.patch("/assistant/notifications/{notification_id}/read")
def api_assistant_notification_read(
    notification_id: int,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    result = mark_notification_read(user.id, notification_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/assistant/notifications/read-all")
def api_assistant_notifications_read_all(
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return mark_all_notifications_read(user.id)


@router.get("/preferences")
def api_preferences_get(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return get_preferences(user.id)


@router.post("/preferences")
def api_preferences_update(
    body: PreferencesBody,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    prefs = body.model_dump(exclude_none=True)
    return update_preferences(user.id, prefs)


@router.get("/daily-briefing")
def api_daily_briefing(
    date: str | None = Query(default=None, alias="date"),
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return get_daily_briefing(user.id, plan_date=date)


@router.get("/assistant/weekly-insights")
def api_weekly_insights(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return get_weekly_insights(user.id)


admin_router = APIRouter(prefix="/admin/assistant", tags=["admin-assistant"])


@admin_router.post("/scan-alerts")
def admin_scan_alerts(
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    return run_alert_scan_job()


@admin_router.get("/aggregate")
def admin_assistant_aggregate(
    _admin: WebAuthUser = Depends(require_admin_user),
) -> dict[str, Any]:
    store = AssistantStore()
    return {"status": "ok", "aggregate": store.admin_aggregate()}
