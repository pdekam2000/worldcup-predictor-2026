"""FastAPI dependencies for authenticated routes."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from worldcup_predictor.access.admin_gate import (
    gate_configured,
    validate_gate_token,
    write_admin_audit_event,
)
from worldcup_predictor.api.web_auth import WebAuthUser, resolve_bearer_token
from worldcup_predictor.auth.rbac import is_admin, is_owner, is_super_admin, role_inherits


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


def require_role(
    minimum_role: str,
    *,
    request: Request | None = None,
    authorization: str | None = None,
    gate: str | None = None,
    gate_token: str | None = None,
) -> WebAuthUser:
    user = get_current_user(authorization)
    if not role_inherits(minimum_role, user.role):
        ip = request.client.host if request and request.client else None
        write_admin_audit_event("unauthorized_route_attempt", user_id=user.id, ip=ip)
        raise HTTPException(status_code=403, detail="Access denied.")
    if gate:
        _require_gate(user, gate, gate_token, request=request)
    return user


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
    if not is_admin(user.role):
        write_admin_audit_event(
            "unauthorized_admin_route_attempt",
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="Access denied.")
    if not is_owner(user.role):
        _require_gate(user, "admin", x_admin_gate_token, request=request)
    return user


def require_super_admin_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_super_admin_gate_token: str | None = Header(default=None, alias="X-Super-Admin-Gate-Token"),
) -> WebAuthUser:
    user = get_current_user(authorization)
    if not is_super_admin(user.role):
        write_admin_audit_event(
            "unauthorized_super_admin_route_attempt",
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="Access denied.")
    if not is_owner(user.role):
        _require_gate(user, "super_admin", x_super_admin_gate_token, request=request)
    return user


def require_owner_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> WebAuthUser:
    user = get_current_user(authorization)
    if not is_owner(user.role):
        write_admin_audit_event(
            "unauthorized_owner_route_attempt",
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="Access denied.")
    return user


def get_optional_current_user(authorization: str | None = Header(default=None)) -> WebAuthUser | None:
    token = _extract_bearer(authorization)
    if not token:
        return None
    return resolve_bearer_token(token)


def user_has_admin_access(role: str) -> bool:
    return is_admin(role)


def user_has_super_admin_access(role: str) -> bool:
    return is_super_admin(role)


def user_has_owner_access(role: str) -> bool:
    return is_owner(role)


def assert_prediction_access(user: WebAuthUser) -> None:
    if user.is_banned or not user.is_active:
        raise HTTPException(status_code=403, detail={"message": "Account is not allowed.", "code": "account_blocked"})
    from worldcup_predictor.auth.verification_config import email_verification_required

    if not email_verification_required() or user.can_access_predictions():
        return
    raise HTTPException(
        status_code=403,
        detail={
            "message": "Email verification required before running predictions.",
            "code": "email_verification_required",
        },
    )


def require_checkout_user(
    authorization: str | None = Header(default=None),
) -> WebAuthUser:
    """Authenticated, verified, non-banned user for Stripe checkout."""
    user = get_current_user(authorization)
    if user.is_banned or not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={"message": "Account is not allowed.", "code": "account_blocked"},
        )
    from worldcup_predictor.auth.verification_config import email_verification_required

    if email_verification_required() and user.role in ("user", "free_user") and not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Email verification required before checkout.",
                "code": "email_verification_required",
            },
        )
    return user
