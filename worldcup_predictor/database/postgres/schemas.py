"""Shared record types returned by PostgreSQL SaaS repositories."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from worldcup_predictor.database.postgres.enums import (
    AlertType,
    BillingCycle,
    FavoriteType,
    NotificationType,
    Prediction1x2,
    PredictionResult,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None


@dataclass(frozen=True)
class UserSettingsRecord:
    user_id: uuid.UUID
    language: str
    timezone: str
    preferences: dict[str, Any]
    updated_at: datetime


@dataclass(frozen=True)
class FavoriteRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    type: FavoriteType
    item_id: str
    item_name: str
    item_meta: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True)
class AlertRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    type: AlertType
    title: str
    message: str
    match_id: int | None
    confidence: Decimal | None
    is_read: bool
    created_at: datetime


@dataclass(frozen=True)
class NotificationRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    title: str
    message: str
    link: str | None
    is_read: bool
    created_at: datetime


@dataclass(frozen=True)
class SubscriptionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    plan: SubscriptionPlan
    billing_cycle: BillingCycle
    status: SubscriptionStatus
    amount: Decimal | None
    external_subscription_id: str | None
    start_date: datetime | None
    end_date: datetime | None
    provider: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PredictionHistoryRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    fixture_id: int
    prediction_id: str | None
    home_team: str
    away_team: str
    league: str | None
    match_date: datetime | None
    prediction_1x2: Prediction1x2
    confidence: Decimal | None
    result: PredictionResult
    viewed_at: datetime
