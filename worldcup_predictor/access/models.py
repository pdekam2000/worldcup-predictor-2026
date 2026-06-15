"""Access control domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class AppUser:
    user_id: str
    email: str | None
    access_token: str
    created_at: str
    is_anonymous: bool = False
    last_login_at: str | None = None


@dataclass
class UserEntitlement:
    user_id: str
    plan: str = "free"
    paid: bool = False
    paid_at: str | None = None
    expires_at: str | None = None
    provider: str | None = None
    payment_reference: str | None = None


@dataclass
class UsageLimit:
    user_id: str
    usage_date: str
    prediction_count: int = 0
    last_prediction_at: str | None = None


@dataclass
class UserFeedback:
    id: int | None
    user_id: str | None
    fixture_id: int | None
    rating: int
    comment: str | None
    prediction_context: str | None
    created_at: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
