"""FastAPI dependencies for authenticated routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from worldcup_predictor.access.admin_gate import (
    gate_configured,
    validate_gate_token,
    write_admin_audit_event,
)
from worldcup_predictor.api.web_auth import WebAuthUser, resolve_bearer_token
from worldcup_predictor.database.postgres.enums import UserRole


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


def _is_admin_role(role: str) -> bool:
    return role in ("admin", "super_admin")


def _is_super_admin_role(role: str) -> bool:
    return role == "super_admin"


def _require_gate(
    user: WebAuthUser,
    gate: str,
    gate_token: str | None,
    *,
    request: Request | None = None,
) -> None:
    if not gate_configured(gate):  # type: ignore[arg-type]
        raise HTTPException(status_code=403, detail="Access denied.")
    if validate_gate_token(gate_token, user_id=user.id, gate=gate):  # type: ignore[arg-type]
        return
    ip = request.client.host if request and request.client else None
    event = "unauthorized_super_admin_route_attempt" if gate == "super_admin" else "unauthorized_admin_route_attempt"
    write_admin_audit_event(event, user_id=user.id, ip=ip)
    raise HTTPException(status_code=403, detail="Access denied.")


def require_admin_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_gate_token: str | None = Header(default=None, alias="X-Admin-Gate-Token"),
) -> WebAuthUser:
    user = get_current_user(authorization)
    if not _is_admin_role(user.role):
        write_admin_audit_event(
            "unauthorized_admin_route_attempt",
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="Access denied.")
    _require_gate(user, "admin", x_admin_gate_token, request=request)
    return user


def require_super_admin_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_super_admin_gate_token: str | None = Header(default=None, alias="X-Super-Admin-Gate-Token"),
) -> WebAuthUser:
    user = get_current_user(authorization)
    if not _is_super_admin_role(user.role):
        write_admin_audit_event(
            "unauthorized_super_admin_route_attempt",
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="Access denied.")
    _require_gate(user, "super_admin", x_super_admin_gate_token, request=request)
    return user


def get_optional_current_user(authorization: str | None = Header(default=None)) -> WebAuthUser | None:
    token = _extract_bearer(authorization)
    if not token:
        return None
    return resolve_bearer_token(token)


def user_has_admin_access(role: str) -> bool:
    return _is_admin_role(role)


def user_has_super_admin_access(role: str) -> bool:
    return _is_super_admin_role(role)


def assert_prediction_access(user: WebAuthUser) -> None:
    if user.is_banned or not user.is_active:
        raise HTTPException(status_code=403, detail={"message": "Account is not allowed.", "code": "account_blocked"})
    if not user.can_access_predictions():
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Email verification required before running predictions.",
                "code": "email_verification_required",
            },
        )
