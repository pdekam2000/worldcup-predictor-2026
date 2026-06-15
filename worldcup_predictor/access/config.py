"""Access control configuration from environment — never hardcode secrets."""

from __future__ import annotations

import os


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_or_secret(key: str, default: str | None = None) -> str | None:
    """Read from os.environ first, then Streamlit secrets (Cloud/Spaces)."""
    val = os.getenv(key)
    if val is not None and str(val).strip():
        return str(val).strip()
    try:
        import streamlit as st

        secrets = st.secrets
        if key in secrets:
            return str(secrets[key]).strip()
        key_lower = key.lower()
        for k in secrets:
            if str(k).lower() == key_lower:
                return str(secrets[k]).strip()
        for section in ("general", "env", "secrets"):
            if section in secrets:
                block = secrets[section]
                if key in block:
                    return str(block[key]).strip()
                for k in block:
                    if str(k).lower() == key_lower:
                        return str(block[k]).strip()
    except Exception:
        pass
    return default


def public_access_enabled() -> bool:
    """When false (default local), limits and paywall are disabled."""
    raw = _env_or_secret("PUBLIC_ACCESS_ENABLED")
    return _truthy(raw, default=False)


def public_access_code() -> str | None:
    """Shared invite code required for public user login."""
    raw = _env_or_secret("PUBLIC_ACCESS_CODE")
    return raw if raw else None


def public_access_config_debug() -> str:
    """Admin-only debug string for live config diagnosis."""
    raw = _env_or_secret("PUBLIC_ACCESS_ENABLED")
    enabled = public_access_enabled()
    code_set = bool(public_access_code())
    source = "env" if os.getenv("PUBLIC_ACCESS_ENABLED") else "secrets/default"
    try:
        import streamlit as st

        if "PUBLIC_ACCESS_ENABLED" in st.secrets:
            source = "st.secrets"
    except Exception:
        pass
    return (
        f"PUBLIC_ACCESS_ENABLED = {str(enabled).lower()} (raw={raw!r}, source={source}) · "
        f"PUBLIC_ACCESS_CODE configured = {str(code_set).lower()}"
    )


def free_daily_prediction_limit() -> int:
    try:
        raw = _env_or_secret("FREE_DAILY_PREDICTION_LIMIT", "2") or "2"
        return max(1, int(raw))
    except ValueError:
        return 2


def paid_unlock_price_eur() -> float:
    try:
        raw = _env_or_secret("PAID_UNLOCK_PRICE_EUR", "5") or "5"
        return float(raw)
    except ValueError:
        return 5.0


def stripe_secret_key() -> str:
    return (_env_or_secret("STRIPE_SECRET_KEY") or "").strip()


def stripe_price_id() -> str:
    return (_env_or_secret("STRIPE_PRICE_ID") or "").strip()


def stripe_payment_link() -> str:
    return (_env_or_secret("STRIPE_PAYMENT_LINK") or "").strip()


def stripe_webhook_secret() -> str:
    return (_env_or_secret("STRIPE_WEBHOOK_SECRET") or "").strip()


def app_public_url() -> str:
    return (_env_or_secret("APP_PUBLIC_URL", "http://localhost:8501") or "http://localhost:8501").rstrip("/")


def access_db_path() -> str | None:
    """Optional override for access-control SQLite file (tests / multi-tenant)."""
    raw = _env_or_secret("ACCESS_DB_PATH") or _env_or_secret("FOOTBALL_DB_PATH")
    return raw or None


def stripe_configured() -> bool:
    if stripe_payment_link():
        return True
    return bool(stripe_secret_key() and stripe_price_id())
