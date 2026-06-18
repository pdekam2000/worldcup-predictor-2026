"""PostgreSQL-backed JWT authentication for the React frontend."""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from typing import Literal

from worldcup_predictor.access.admin_auth import admin_username_normalized, verify_admin_credentials
from worldcup_predictor.access.config import public_access_code
from worldcup_predictor.access.repository import normalize_user_identity
from worldcup_predictor.auth.jwt_tokens import TokenError, create_access_token, decode_access_token
from worldcup_predictor.auth.passwords import hash_password, verify_password
from worldcup_predictor.database.postgres.enums import UserRole
from worldcup_predictor.database.postgres.schemas import UserRecord
from worldcup_predictor.database.saas_factory import saas_uow

LoginRole = Literal["admin", "user"]
MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class WebAuthUser:
    id: str
    email: str | None
    full_name: str
    role: LoginRole

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "email": self.email or "",
            "full_name": self.full_name,
            "role": self.role,
        }


def _to_web_user(record: UserRecord) -> WebAuthUser:
    return WebAuthUser(
        id=str(record.id),
        email=record.email,
        full_name=record.full_name or record.email,
        role="admin" if record.role == UserRole.ADMIN else "user",
    )


def invite_code_required() -> bool:
    return bool((public_access_code() or "").strip())


def verify_invite_code(invite_code: str | None) -> bool:
    expected = (public_access_code() or "").strip()
    if not expected:
        return True
    provided = (invite_code or "").strip()
    return bool(provided and hmac.compare_digest(provided, expected))


def _provision_new_user(uow, record: UserRecord) -> UserRecord:
    uow.settings.get_or_create(record.id)
    uow.subscriptions.get_or_create_free(record.id)
    return record


def _admin_bootstrap_login(uow, email: str, password: str) -> UserRecord | None:
    normalized = normalize_user_identity(email) or ""
    if normalized != admin_username_normalized():
        return None
    if not verify_admin_credentials(normalized, password):
        return None
    pwd_hash = hash_password(password)
    existing = uow.users.get_by_email(normalized)
    if existing is None:
        record = uow.users.create(
            email=normalized,
            password_hash=pwd_hash,
            full_name="Administrator",
            role=UserRole.ADMIN,
        )
        return _provision_new_user(uow, record)
    uow.users.update_password_hash(existing.id, pwd_hash)
    updated = uow.users.set_role(existing.id, UserRole.ADMIN)
    return updated or existing


def register_with_password(
    *,
    email: str,
    password: str,
    invite_code: str | None = None,
) -> tuple[WebAuthUser | None, str | None]:
    normalized = normalize_user_identity(email) or ""
    pwd = (password or "").strip()
    if not normalized:
        return None, "Email is required."
    if "@" not in normalized and normalized == admin_username_normalized():
        return None, "Use the login page for admin accounts."
    if len(pwd) < MIN_PASSWORD_LENGTH:
        return None, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if invite_code_required() and not verify_invite_code(invite_code):
        return None, "Invalid or missing invite code."

    with saas_uow() as uow:
        if uow.users.get_by_email(normalized):
            return None, "Email already registered."
        record = uow.users.create(
            email=normalized,
            password_hash=hash_password(pwd),
            full_name=normalized.split("@")[0],
            role=UserRole.USER,
        )
        record = _provision_new_user(uow, record)
        uow.users.touch_login(record.id)
        return _to_web_user(record), None


def login_with_password(
    *,
    email: str,
    password: str,
) -> tuple[WebAuthUser | None, str | None]:
    normalized = normalize_user_identity(email) or ""
    pwd = (password or "").strip()
    if not normalized:
        return None, "Email or username is required."
    if not pwd:
        return None, "Password is required."

    with saas_uow() as uow:
        admin_record = _admin_bootstrap_login(uow, normalized, pwd)
        if admin_record is not None:
            uow.users.touch_login(admin_record.id)
            return _to_web_user(admin_record), None

        record = uow.users.verify_email_password(normalized, pwd, verify_password)
        if record is None:
            return None, "Invalid email or password."
        if not record.is_active:
            return None, "Account is disabled."
        uow.users.touch_login(record.id)
        return _to_web_user(record), None


def issue_access_token(user: WebAuthUser) -> str:
    role = UserRole.ADMIN if user.role == "admin" else UserRole.USER
    return create_access_token(
        user_id=uuid.UUID(user.id),
        email=user.email or "",
        role=role,
    )


def resolve_bearer_token(token: str) -> WebAuthUser | None:
    if not token or not token.strip():
        return None
    try:
        payload = decode_access_token(token.strip())
    except TokenError:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError:
        return None
    with saas_uow() as uow:
        record = uow.users.get_by_id(user_id)
        if record is None or not record.is_active:
            return None
        return _to_web_user(record)


def user_profile(user: WebAuthUser) -> WebAuthUser:
    return user


def revoke_session_token(token: str) -> None:
    """JWT logout is client-side; kept for API compatibility."""
    return None


# Backwards-compatible aliases for route module
issue_session_token = issue_access_token
