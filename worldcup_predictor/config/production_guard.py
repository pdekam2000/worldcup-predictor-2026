"""Production configuration validation — fail fast on unsafe deploy settings."""

from __future__ import annotations

import os
import re

from worldcup_predictor.access.config import public_access_code
from worldcup_predictor.config.settings import Settings

_INSECURE_JWT_MARKERS = (
    "dev-only-change-in-production",
    "dev-phase2-jwt-secret",
    "change-in-production",
    "changeme",
    "secret",
)


def _admin_password() -> str:
    return (os.getenv("ADMIN_PASSWORD") or "").strip()


def _admin_username() -> str:
    return (os.getenv("ADMIN_USERNAME") or "").strip()


def validate_production_settings(settings: Settings) -> list[str]:
    """Return human-readable errors; empty list means production-ready."""
    if not settings.is_production:
        return []

    errors: list[str] = []

    if not settings.postgres_configured:
        errors.append("DATABASE_URL is required when APP_ENV=production")

    if not settings.api_football_key.strip():
        errors.append("API_FOOTBALL_KEY is required when APP_ENV=production")

    jwt = (settings.jwt_secret or "").strip()
    if len(jwt) < 32:
        errors.append("JWT_SECRET must be at least 32 characters in production")
    elif any(marker in jwt.lower() for marker in _INSECURE_JWT_MARKERS):
        errors.append("JWT_SECRET appears to be a development placeholder — set a unique production secret")

    if not _admin_username():
        errors.append("ADMIN_USERNAME is required when APP_ENV=production")
    if not _admin_password():
        errors.append("ADMIN_PASSWORD is required when APP_ENV=production")
    elif len(_admin_password()) < 12:
        errors.append("ADMIN_PASSWORD should be at least 12 characters in production")

    invite = (public_access_code() or "").strip()
    if not invite:
        errors.append("PUBLIC_ACCESS_CODE is recommended in production (registration gate)")

    cors = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if cors:
        for origin in cors.split(","):
            o = origin.strip()
            if re.match(r"https?://(localhost|127\.0\.0\.1)", o, re.I):
                errors.append(f"CORS_ALLOWED_ORIGINS must not include localhost in production: {o}")

    if settings.database_fallback_enabled and settings.is_production:
        # Informational — SQLite intelligence DB is still used for predictions locally on server
        pass

    return errors


def assert_production_ready(settings: Settings) -> None:
    errors = validate_production_settings(settings)
    if errors:
        joined = "; ".join(errors)
        raise RuntimeError(f"Production configuration invalid: {joined}")
