"""Authenticated SaaS user routes — settings, favorites, alerts, notifications, history."""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.saas_serializers import (
    alert_to_dict,
    favorite_to_dict,
    notification_to_dict,
    parse_uuid,
    prediction_history_to_dict,
    settings_to_dict,
    subscription_to_dict,
)
from worldcup_predictor.api.web_auth import WebAuthUser
from worldcup_predictor.database.postgres.enums import FavoriteType, Prediction1x2, PredictionResult
from worldcup_predictor.database.saas_factory import saas_uow

router = APIRouter(prefix="/user", tags=["user"])


def _user_id(user: WebAuthUser) -> uuid.UUID:
    return parse_uuid(user.id, field="user id")


class SettingsPatchRequest(BaseModel):
    language: str | None = Field(default=None, max_length=16)
    timezone: str | None = Field(default=None, max_length=64)
    preferences: dict[str, Any] | None = None


class FavoriteCreateRequest(BaseModel):
    type: str = Field(..., pattern="^(team|league|match)$")
    item_id: str = Field(..., min_length=1, max_length=128)
    item_name: str = Field(..., min_length=1, max_length=256)
    item_meta: str | None = Field(default=None, max_length=256)


class PredictionHistoryCreateRequest(BaseModel):
    fixture_id: int
    home_team: str
    away_team: str
    prediction_1x2: str = Field(..., pattern="^(home|draw|away)$")
    league: str | None = None
    confidence: float | None = None


def _dashboard_stats(history: list) -> dict[str, Any]:
    total = len(history)
    settled = [h for h in history if h.result != PredictionResult.PENDING]
    correct = sum(1 for h in settled if h.result == PredictionResult.CORRECT)
    win_rate = round((correct / len(settled)) * 100, 1) if settled else 0.0

    streak = 0
    for row in history:
        if row.result == PredictionResult.CORRECT:
            streak += 1
        elif row.result == PredictionResult.INCORRECT:
            break

    by_month: dict[str, list[int]] = defaultdict(list)
    for row in history:
        if row.viewed_at and row.result != PredictionResult.PENDING:
            key = row.viewed_at.strftime("%b")
            by_month[key].append(1 if row.result == PredictionResult.CORRECT else 0)

    trend = [
        {"month": month, "accuracy": round(sum(vals) / len(vals) * 100, 1)}
        for month, vals in sorted(by_month.items(), key=lambda item: item[0])
    ][-6:]

    return {
        "predictions_viewed": total,
        "win_rate": win_rate,
        "matches_analyzed": total,
        "streak": f"{streak}W" if streak else "0",
        "streak_count": streak,
        "correct": correct,
        "settled": len(settled),
        "performance_trend": trend,
    }


@router.get("/settings")
def get_settings(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        record = uow.settings.get_or_create(_user_id(user))
        return {"status": "ok", "settings": settings_to_dict(record)}


@router.patch("/settings")
def patch_settings(
    body: SettingsPatchRequest,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    uid = _user_id(user)
    with saas_uow() as uow:
        current = uow.settings.get_or_create(uid)
        merged_prefs = dict(current.preferences or {})
        if body.preferences is not None:
            merged_prefs.update(body.preferences)
        record = uow.settings.upsert(
            uid,
            language=body.language,
            timezone=body.timezone,
            preferences=merged_prefs if body.preferences is not None else None,
        )
        return {"status": "ok", "settings": settings_to_dict(record)}


@router.get("/favorites")
def list_favorites(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        rows = uow.favorites.list_for_user(_user_id(user))
        return {"status": "ok", "favorites": [favorite_to_dict(row) for row in rows]}


@router.post("/favorites")
def add_favorite(
    body: FavoriteCreateRequest,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    uid = _user_id(user)
    meta = {"subtitle": body.item_meta} if body.item_meta else None
    try:
        fav_type = FavoriteType(body.type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid favorite type") from exc

    with saas_uow() as uow:
        try:
            record = uow.favorites.add(
                uid,
                type=fav_type,
                item_id=body.item_id,
                item_name=body.item_name,
                item_meta=meta,
            )
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Favorite already exists") from exc
        return {"status": "ok", "favorite": favorite_to_dict(record)}


@router.delete("/favorites/{favorite_id}")
def delete_favorite(
    favorite_id: str,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        fid = parse_uuid(favorite_id, field="favorite id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        if not uow.favorites.delete(_user_id(user), fid):
            raise HTTPException(status_code=404, detail="Favorite not found")
        return {"status": "ok"}


@router.get("/alerts")
def list_alerts(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        rows = uow.alerts.list_for_user(_user_id(user))
        items = [alert_to_dict(row) for row in rows]
        unread = sum(1 for row in rows if not row.is_read)
        return {"status": "ok", "alerts": items, "unread_count": unread}


@router.patch("/alerts/{alert_id}/read")
def mark_alert_read(
    alert_id: str,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        aid = parse_uuid(alert_id, field="alert id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        if not uow.alerts.mark_read(_user_id(user), aid):
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"status": "ok"}


@router.post("/alerts/read-all")
def mark_all_alerts_read(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        count = uow.alerts.mark_all_read(_user_id(user))
        return {"status": "ok", "updated": count}


@router.get("/notifications")
def list_notifications(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        rows = uow.notifications.list_for_user(_user_id(user))
        items = [notification_to_dict(row) for row in rows]
        unread = sum(1 for row in rows if not row.is_read)
        return {"status": "ok", "notifications": items, "unread_count": unread}


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        nid = parse_uuid(notification_id, field="notification id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with saas_uow() as uow:
        if not uow.notifications.mark_read(_user_id(user), nid):
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "ok"}


@router.post("/notifications/read-all")
def mark_all_notifications_read(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        count = uow.notifications.mark_all_read(_user_id(user))
        return {"status": "ok", "updated": count}


@router.get("/prediction-history")
def list_prediction_history(
    limit: int = 50,
    offset: int = 0,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    with saas_uow() as uow:
        rows = uow.prediction_history.list_for_user(_user_id(user), limit=limit, offset=offset)
        items = [prediction_history_to_dict(row) for row in rows]
        settled = [row for row in rows if row.result != PredictionResult.PENDING]
        correct = sum(1 for row in settled if row.result == PredictionResult.CORRECT)
        accuracy = round((correct / len(settled)) * 100, 1) if settled else 0.0
        return {
            "status": "ok",
            "history": items,
            "stats": {
                "total": len(items),
                "correct": correct,
                "accuracy": accuracy,
            },
        }


@router.post("/prediction-history")
def record_prediction_history(
    body: PredictionHistoryCreateRequest,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        pick = Prediction1x2(body.prediction_1x2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid prediction") from exc

    confidence = Decimal(str(body.confidence)) if body.confidence is not None else None
    with saas_uow() as uow:
        record = uow.prediction_history.add(
            _user_id(user),
            fixture_id=body.fixture_id,
            home_team=body.home_team,
            away_team=body.away_team,
            prediction_1x2=pick,
            league=body.league,
            confidence=confidence,
            result=PredictionResult.PENDING,
        )
        return {"status": "ok", "entry": prediction_history_to_dict(record)}


@router.get("/subscription")
def get_subscription(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        record = uow.subscriptions.get_or_create_free(_user_id(user))
        return {
            "status": "ok",
            "subscription": subscription_to_dict(record),
            "billing_history": [],
        }


@router.get("/dashboard")
def get_dashboard(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        history = uow.prediction_history.list_for_user(_user_id(user), limit=50)
        stats = _dashboard_stats(history)
        trend = stats.pop("performance_trend", [])
        recent = [prediction_history_to_dict(row) for row in history[:5]]
        return {
            "status": "ok",
            "stats": stats,
            "recent_predictions": recent,
            "performance_trend": trend,
        }
