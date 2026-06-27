"""PostgreSQL-backed JWT authentication for the React frontend."""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from worldcup_predictor.access.admin_auth import admin_username_normalized, verify_admin_credentials
from worldcup_predictor.access.config import public_access_code
from worldcup_predictor.access.repository import normalize_user_identity
from worldcup_predictor.auth.email_verification import issue_verification_token
from worldcup_predictor.auth.jwt_tokens import TokenError, create_access_token, decode_access_token
from worldcup_predictor.auth.passwords import hash_password, verify_password
from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
from worldcup_predictor.database.postgres.schemas import UserRecord
from worldcup_predictor.database.saas_factory import saas_uow

LoginRole = Literal["admin", "user", "super_admin"]
MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class WebAuthUser:
    id: str
    email: str | None
    full_name: str
    role: LoginRole
    email_verified: bool = False
    is_banned: bool = False
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email or "",
            "full_name": self.full_name,
            "role": self.role,
            "email_verified": self.email_verified,
            "is_banned": self.is_banned,
            "is_active": self.is_active,
        }

    def can_access_predictions(self) -> bool:
        if self.is_banned or not self.is_active:
            return False
        if self.role in ("admin", "super_admin"):
            return True
        return self.email_verified


def _to_web_user(record: UserRecord) -> WebAuthUser:
    if record.role == UserRole.SUPER_ADMIN:
        role: LoginRole = "super_admin"
    elif record.role == UserRole.ADMIN:
        role = "admin"
    else:
        role = "user"
    return WebAuthUser(
        id=str(record.id),
        email=record.email,
        full_name=record.full_name or record.email,
        role=role,
        email_verified=record.email_verified,
        is_banned=record.is_banned,
        is_active=record.is_active,
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
            email_verified=True,
        )
        return _provision_new_user(uow, record)
    uow.users.update_password_hash(existing.id, pwd_hash)
    uow.users.set_email_verified(existing.id, True)
    updated = uow.users.set_role(existing.id, UserRole.ADMIN)
    return updated or existing


def register_with_password(
    *,
    email: str,
    password: str,
    invite_code: str | None = None,
) -> tuple[WebAuthUser | None, str | None, bool]:
    """Return (profile, error, verification_required)."""
    normalized = normalize_user_identity(email) or ""
    pwd = (password or "").strip()
    if not normalized:
        return None, "Email is required.", False
    if "@" not in normalized and normalized == admin_username_normalized():
        return None, "Use the login page for admin accounts.", False
    if len(pwd) < MIN_PASSWORD_LENGTH:
        return None, f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", False
    if invite_code_required() and not verify_invite_code(invite_code):
        return None, "Invalid or missing invite code.", False

    with saas_uow() as uow:
        if uow.users.get_by_email(normalized):
            return None, "Email already registered.", False
        record = uow.users.create(
            email=normalized,
            password_hash=hash_password(pwd),
            full_name=normalized.split("@")[0],
            role=UserRole.USER,
            email_verified=False,
        )
        record = _provision_new_user(uow, record)
    issue_verification_token(record.id, email=record.email)
    return _to_web_user(record), None, True


def login_with_password(
    *,
    email: str,
    password: str,
) -> tuple[WebAuthUser | None, str | None, str | None]:
    """Return (profile, error, error_code). error_code may be 'banned' or 'email_verification_required'."""
    normalized = normalize_user_identity(email) or ""
    pwd = (password or "").strip()
    if not normalized:
        return None, "Email or username is required.", None
    if not pwd:
        return None, "Password is required.", None

    with saas_uow() as uow:
        admin_record = _admin_bootstrap_login(uow, normalized, pwd)
        if admin_record is not None:
            if admin_record.is_banned:
                return None, "Account has been banned.", "banned"
            uow.users.touch_login(admin_record.id)
            return _to_web_user(admin_record), None, None

        record = uow.users.verify_email_password(normalized, pwd, verify_password)
        if record is None:
            return None, "Invalid email or password.", None
        if record.is_banned:
            return None, "Account has been banned.", "banned"
        if not record.is_active:
            return None, "Account is disabled.", "disabled"
        uow.users.touch_login(record.id)
        profile = _to_web_user(record)
        if not profile.email_verified and profile.role == "user":
            return profile, None, "email_verification_required"
        return profile, None, None


def issue_access_token(user: WebAuthUser, *, token_version: int = 0) -> str:
    if user.role == "super_admin":
        role = UserRole.SUPER_ADMIN
    elif user.role == "admin":
        role = UserRole.ADMIN
    else:
        role = UserRole.USER
    return create_access_token(
        user_id=uuid.UUID(user.id),
        email=user.email or "",
        role=role,
        token_version=token_version,
    )


def issue_access_token_for_record(record: UserRecord) -> str:
    user = _to_web_user(record)
    return issue_access_token(user, token_version=record.token_version)


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
    token_tv = int(payload.get("tv") or 0)
    with saas_uow() as uow:
        record = uow.users.get_by_id(user_id)
        if record is None or not record.is_active or record.is_banned:
            return None
        if int(record.token_version or 0) != token_tv:
            return None
        return _to_web_user(record)


def user_profile(user: WebAuthUser) -> WebAuthUser:
    return user


def revoke_session_token(token: str) -> None:
    """JWT logout is client-side; kick uses token_version bump."""
    return None


def seed_owner_account(
    *,
    email: str,
    password_hash: str,
    full_name: str | None = None,
    plan: SubscriptionPlan = SubscriptionPlan.PRO,
) -> UserRecord:
    normalized = email.strip().lower()
    with saas_uow() as uow:
        existing = uow.users.get_by_email(normalized)
        if existing is None:
            record = uow.users.create(
                email=normalized,
                password_hash=password_hash,
                full_name=full_name or normalized.split("@")[0],
                role=UserRole.SUPER_ADMIN,
                email_verified=True,
            )
        else:
            uow.users.update_password_hash(existing.id, password_hash)
            uow.users.set_email_verified(existing.id, True)
            uow.users.clear_ban(existing.id)
            record = uow.users.set_role(existing.id, UserRole.SUPER_ADMIN) or existing
        uow.settings.get_or_create(record.id)
        uow.subscriptions.upsert(record.id, plan=plan)
        return record


# Backwards-compatible aliases for route module
issue_session_token = issue_access_token
