"""Serialize PostgreSQL SaaS records for JSON API responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from worldcup_predictor.database.postgres.schemas import (
    AlertRecord,
    FavoriteRecord,
    NotificationRecord,
    PredictionHistoryRecord,
    SubscriptionRecord,
    UserRecord,
    UserSettingsRecord,
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _num(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _enum(value: Enum | str | None) -> str | None:
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)


def settings_to_dict(record: UserSettingsRecord) -> dict[str, Any]:
    return {
        "language": record.language,
        "timezone": record.timezone,
        "preferences": dict(record.preferences or {}),
        "updated_at": _iso(record.updated_at),
    }


def favorite_to_dict(record: FavoriteRecord) -> dict[str, Any]:
    meta = record.item_meta or {}
    subtitle = meta.get("subtitle") or meta.get("league") or meta.get("country") or ""
    return {
        "id": str(record.id),
        "type": _enum(record.type),
        "item_id": record.item_id,
        "item_name": record.item_name,
        "item_meta": subtitle or None,
        "item_meta_raw": meta,
        "created_at": _iso(record.created_at),
    }


def alert_to_dict(record: AlertRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "type": _enum(record.type),
        "title": record.title,
        "message": record.message,
        "match_id": record.match_id,
        "confidence": _num(record.confidence),
        "is_read": record.is_read,
        "created_at": _iso(record.created_at),
        "created_date": _iso(record.created_at),
    }


def notification_to_dict(record: NotificationRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "type": _enum(record.type),
        "title": record.title,
        "message": record.message,
        "link": record.link,
        "is_read": record.is_read,
        "created_at": _iso(record.created_at),
        "created_date": _iso(record.created_at),
    }


def subscription_to_dict(record: SubscriptionRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "plan": _enum(record.plan),
        "billing_cycle": _enum(record.billing_cycle),
        "status": _enum(record.status),
        "amount": _num(record.amount),
        "external_subscription_id": record.external_subscription_id,
        "start_date": _iso(record.start_date),
        "end_date": _iso(record.end_date),
        "provider": record.provider,
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
    }


def prediction_history_to_dict(record: PredictionHistoryRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "fixture_id": record.fixture_id,
        "prediction_id": record.prediction_id,
        "home_team": record.home_team,
        "away_team": record.away_team,
        "league": record.league,
        "match_date": _iso(record.match_date),
        "prediction_1x2": _enum(record.prediction_1x2),
        "confidence": _num(record.confidence),
        "result": _enum(record.result),
        "viewed_at": _iso(record.viewed_at),
    }


def user_admin_to_dict(
    record: UserRecord,
    *,
    plan: str = "free",
    predictions_used_month: int | None = None,
) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "email": record.email,
        "full_name": record.full_name or record.email,
        "role": _enum(record.role),
        "plan": plan,
        "is_active": record.is_active,
        "email_verified": record.email_verified,
        "is_banned": record.is_banned,
        "banned_at": _iso(record.banned_at),
        "banned_reason": record.banned_reason,
        "created_at": _iso(record.created_at),
        "created_date": record.created_at.date().isoformat() if record.created_at else None,
        "last_login_at": _iso(record.last_login_at),
        "predictions_used_month": predictions_used_month,
    }


def parse_uuid(value: str, *, field: str = "id") -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}") from exc
