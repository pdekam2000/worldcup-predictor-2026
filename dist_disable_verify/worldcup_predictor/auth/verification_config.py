"""Email verification requirement toggle (EMAIL_VERIFICATION_REQUIRED env)."""

from __future__ import annotations

from worldcup_predictor.config.settings import Settings, get_settings


def email_verification_required(settings: Settings | None = None) -> bool:
    """When False, registration auto-verifies and login is not blocked by email_verified."""
    s = settings or get_settings()
    return bool(getattr(s, "email_verification_required", True))
