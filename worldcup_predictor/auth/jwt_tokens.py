"""JWT access tokens for FastAPI authentication."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.enums import UserRole


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or validated."""


def _settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def _secret(settings: Settings) -> str:
    secret = (settings.jwt_secret or "").strip()
    if not secret:
        raise TokenError("JWT_SECRET is not configured.")
    return secret


def create_access_token(
    *,
    user_id: uuid.UUID,
    email: str,
    role: UserRole,
    settings: Settings | None = None,
) -> str:
    active = _settings(settings)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=active.jwt_access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, _secret(active), algorithm=active.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    active = _settings(settings)
    try:
        payload = jwt.decode(
            token,
            _secret(active),
            algorithms=[active.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired token.") from exc
    if payload.get("type") != "access":
        raise TokenError("Invalid token type.")
    return payload
