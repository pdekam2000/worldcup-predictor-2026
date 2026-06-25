"""Authenticated SaaS user routes — settings, favorites, alerts, notifications, history."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from worldcup_predictor.api.deps import get_current_user
from worldcup_predictor.api.prediction_archive_detail import fetch_archive_detail_for_user
from worldcup_predictor.api.prediction_history_evaluation import (
    evaluate_history_record,
    filter_by_result_status,
)
from worldcup_predictor.api.saas_serializers import (
    alert_to_dict,
    favorite_to_dict,
    notification_to_dict,
    parse_uuid,
    prediction_history_to_dict,
    settings_to_dict,
    subscription_to_dict,
)
from worldcup_predictor.config.settings import get_settings as get_app_settings
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


def _dashboard_stats_from_evaluated(history: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(history)
    settled = [h for h in history if h.get("result_status") in ("correct", "wrong")]
    correct = sum(1 for h in settled if h.get("result_status") == "correct")
    win_rate = round((correct / len(settled)) * 100, 1) if settled else 0.0

    streak = 0
    for row in history:
        if row.get("result_status") == "correct":
            streak += 1
        elif row.get("result_status") == "wrong":
            break

    by_month: dict[str, list[int]] = defaultdict(list)
    for row in history:
        if row.get("result_status") not in ("correct", "wrong"):
            continue
        viewed = row.get("viewed_at")
        if not viewed:
            continue
        try:
            month_key = datetime.fromisoformat(str(viewed).replace("Z", "+00:00")).strftime("%b")
        except ValueError:
            continue
        by_month[month_key].append(1 if row.get("result_status") == "correct" else 0)

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
def read_user_settings(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    with saas_uow() as uow:
        record = uow.settings.get_or_create(_user_id(user))
        return {"status": "ok", "settings": settings_to_dict(record)}


@router.patch("/settings")
def update_user_settings(
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
    result_filter: str = "all",
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    settings = get_app_settings()
    with saas_uow() as uow:
        rows = uow.prediction_history.list_for_user(_user_id(user), limit=limit, offset=offset)
        from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver

        resolver = FixtureOutcomeResolver(settings=settings)
        items = [evaluate_history_record(row, resolver=resolver, settings=settings) for row in rows]
        filtered = filter_by_result_status(items, result_filter)

        settled = [item for item in items if item.get("result_status") in ("correct", "wrong")]
        correct = sum(1 for item in settled if item.get("result_status") == "correct")
        wrong = sum(1 for item in settled if item.get("result_status") == "wrong")
        pending = sum(1 for item in items if item.get("result_status") == "pending")
        unknown = sum(1 for item in items if item.get("result_status") == "unknown")
        accuracy = round((correct / len(settled)) * 100, 1) if settled else 0.0
        return {
            "status": "ok",
            "history": filtered,
            "stats": {
                "total": len(items),
                "correct": correct,
                "wrong": wrong,
                "pending": pending,
                "unknown": unknown,
                "accuracy": accuracy,
            },
        }


@router.get("/prediction-history/results")
def list_prediction_history_results(
    limit: int = 50,
    offset: int = 0,
    result_filter: str = "all",
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase 29 — explicit results endpoint (same payload as enriched prediction-history)."""
    return list_prediction_history(
        limit=limit,
        offset=offset,
        result_filter=result_filter,
        user=user,
    )


@router.get("/prediction-history/{entry_id}")
def get_prediction_history_entry(
    entry_id: str,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase 42C — archive detail for one history row."""
    entry_uuid = parse_uuid(entry_id, field="entry id")
    detail = fetch_archive_detail_for_user(_user_id(user), entry_uuid, settings=get_app_settings())
    if detail is None:
        raise HTTPException(status_code=404, detail="Prediction history entry not found")
    return detail


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
    from worldcup_predictor.billing.billing_serializers import format_invoice_for_legacy_table
    from worldcup_predictor.billing.billing_service import get_billing_service
    from worldcup_predictor.subscription.plan_limits import PLAN_FEATURES, PLAN_PRICES_EUR, normalize_plan

    with saas_uow() as uow:
        record = uow.subscriptions.get_or_create_free(_user_id(user))

    plan_key = normalize_plan(record.plan.value if record else "free")
    with saas_uow() as uow:
        invoice_items = uow.billing_invoices.list_for_user(_user_id(user), limit=20)
    billing_history = [format_invoice_for_legacy_table(item) for item in invoice_items]

    return {
        "status": "ok",
        "subscription": subscription_to_dict(record),
        "features": PLAN_FEATURES.get(plan_key, PLAN_FEATURES["free"]),
        "price_eur": PLAN_PRICES_EUR.get(plan_key, 0),
        "billing_history": billing_history,
    }


@router.get("/quota")
def get_user_quota(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    from worldcup_predictor.subscription.quota_service import get_user_quota_status
    from worldcup_predictor.subscription.plan_limits import PLAN_FEATURES, PLAN_PRICES_EUR, normalize_plan

    quota = get_user_quota_status(user.id, role=user.role)
    plan = normalize_plan(quota.plan)
    limit = quota.monthly_limit or 0
    used = quota.used_this_period or 0
    percent_used = round((used / limit) * 100, 1) if limit > 0 and not quota.bypass else 0.0
    quota_warning = None
    if not quota.bypass and limit > 0:
        if used >= limit:
            quota_warning = "exhausted"
        elif percent_used >= 90:
            quota_warning = "critical"
        elif percent_used >= 75:
            quota_warning = "warning"

    return {
        "status": "ok",
        "plan": quota.plan,
        "monthly_limit": quota.monthly_limit,
        "used_this_period": quota.used_this_period,
        "remaining": quota.remaining,
        "percent_used": percent_used,
        "quota_warning": quota_warning,
        "period_key": quota.period_key,
        "period_start": quota.period_start,
        "period_end": quota.period_end,
        "next_reset_date": quota.period_end,
        "bypass": quota.bypass,
        "allowed": quota.allowed,
        "price_eur": PLAN_PRICES_EUR.get(plan, 0),
        "features": PLAN_FEATURES.get(plan, PLAN_FEATURES["free"]),
        # Legacy fields for older frontend
        "daily_limit": quota.monthly_limit,
        "used_today": quota.used_this_period,
    }


class ContactAdminRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    category: str = Field(
        default="other",
        pattern="^(support|subscription|billing|prediction_issue|feature_request|other)$",
    )


@router.post("/contact-admin")
def contact_admin(
    body: ContactAdminRequest,
    request: Request,
    user: WebAuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    from worldcup_predictor.subscription.contact_admin import (
        ContactAdminRateLimitError,
        submit_contact_admin,
    )

    ip = request.client.host if request.client else None
    try:
        submit_contact_admin(
            user_id=user.id,
            user_email=user.email,
            subject=body.subject,
            message=body.message,
            category=body.category,
            ip=ip,
        )
    except ContactAdminRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail={"message": str(exc), "retry_after_seconds": exc.retry_after_seconds},
        ) from exc
    return {"status": "ok", "message": "Message sent successfully"}


def _empty_dashboard_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "stats": {
            "predictions_viewed": 0,
            "win_rate": 0.0,
            "matches_analyzed": 0,
            "streak": "0",
            "streak_count": 0,
            "correct": 0,
            "settled": 0,
        },
        "recent_predictions": [],
        "performance_trend": [],
    }


@router.get("/dashboard")
def get_dashboard(user: WebAuthUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        settings = get_app_settings()
        with saas_uow() as uow:
            history = uow.prediction_history.list_for_user(_user_id(user), limit=50)
            from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver

            resolver = FixtureOutcomeResolver(settings=settings)
            evaluated = []
            for row in history:
                try:
                    evaluated.append(evaluate_history_record(row, resolver=resolver, settings=settings))
                except Exception:
                    continue
            stats = _dashboard_stats_from_evaluated(evaluated)
            trend = stats.pop("performance_trend", [])
            recent = evaluated[:5]
            return {
                "status": "ok",
                "stats": stats,
                "recent_predictions": recent,
                "performance_trend": trend,
            }
    except Exception:
        return _empty_dashboard_payload()
