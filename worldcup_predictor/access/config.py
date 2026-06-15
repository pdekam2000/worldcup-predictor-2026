"""Access control configuration from environment — never hardcode secrets."""

from __future__ import annotations

import os


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def public_access_enabled() -> bool:
    """When false (default local), limits and paywall are disabled."""
    return _truthy(os.getenv("PUBLIC_ACCESS_ENABLED"), default=False)


def free_daily_prediction_limit() -> int:
    try:
        return max(1, int(os.getenv("FREE_DAILY_PREDICTION_LIMIT", "2")))
    except ValueError:
        return 2


def paid_unlock_price_eur() -> float:
    try:
        return float(os.getenv("PAID_UNLOCK_PRICE_EUR", "5"))
    except ValueError:
        return 5.0


def stripe_secret_key() -> str:
    return (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def stripe_price_id() -> str:
    return (os.getenv("STRIPE_PRICE_ID") or "").strip()


def stripe_payment_link() -> str:
    return (os.getenv("STRIPE_PAYMENT_LINK") or "").strip()


def stripe_webhook_secret() -> str:
    return (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()


def app_public_url() -> str:
    return (os.getenv("APP_PUBLIC_URL") or "http://localhost:8501").strip().rstrip("/")


def access_db_path() -> str | None:
    """Optional override for access-control SQLite file (tests / multi-tenant)."""
    return (os.getenv("ACCESS_DB_PATH") or os.getenv("FOOTBALL_DB_PATH") or "").strip() or None


def stripe_configured() -> bool:
    if stripe_payment_link():
        return True
    return bool(stripe_secret_key() and stripe_price_id())
