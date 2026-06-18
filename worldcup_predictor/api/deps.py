"""FastAPI dependencies for authenticated routes."""

from __future__ import annotations

from fastapi import Header, HTTPException

from worldcup_predictor.api.web_auth import WebAuthUser, resolve_bearer_token


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user(authorization: str | None = Header(default=None)) -> WebAuthUser:
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = resolve_bearer_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_admin_user(authorization: str | None = Header(default=None)) -> WebAuthUser:
    user = get_current_user(authorization)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def get_optional_current_user(authorization: str | None = Header(default=None)) -> WebAuthUser | None:
    token = _extract_bearer(authorization)
    if not token:
        return None
    return resolve_bearer_token(token)
