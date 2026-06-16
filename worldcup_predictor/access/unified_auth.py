"""Unified GUI login — username + password for admin and regular users."""

from __future__ import annotations

import hmac
import secrets
from typing import Literal

import streamlit as st

from worldcup_predictor.access.admin_auth import (
    acquire_admin_session_lock,
    admin_credentials,
    admin_username_normalized,
    is_admin_session,
    login_admin,
    logout_admin,
    release_admin_session_lock,
    verify_admin_credentials,
)
from worldcup_predictor.access.config import (
    credentials_login_available,
    public_access_code,
    public_access_enabled,
)
from worldcup_predictor.access.identity import (
    _set_registered_session,
    init_access_session,
    logout_user,
)
from worldcup_predictor.access.models import AppUser
from worldcup_predictor.access.repository import get_access_repository, normalize_user_identity

LoginRole = Literal["admin", "user"]


def _session_admin_token() -> str:
    token = st.session_state.get("admin_session_token")
    if not token:
        token = secrets.token_urlsafe(24)
        st.session_state["admin_session_token"] = token
    return str(token)


def verify_gui_password(password: str) -> bool:
    """Regular user password — PUBLIC_ACCESS_CODE from env."""
    expected = public_access_code()
    provided = (password or "").strip()
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def is_admin_username(username: str) -> bool:
    normalized = normalize_user_identity(username or "")
    if not normalized:
        return False
    return normalized == admin_username_normalized()


def login_gui(
    *,
    username: str,
    password: str,
    remember_me: bool = False,
) -> tuple[AppUser | None, str | None, LoginRole | None]:
    """Single login entry — returns (user, error_i18n_key, role)."""
    if not credentials_login_available():
        return None, "access.invite_not_configured", None

    normalized = normalize_user_identity(username or "")
    pwd = (password or "").strip()
    if not normalized:
        return None, "access.username_required", None
    if not pwd:
        return None, "access.password_required", None

    if is_admin_username(normalized):
        if not verify_admin_credentials(normalized, pwd):
            return None, "admin.login_fail", None
        token = _session_admin_token()
        login_admin(normalized, pwd)
        acquire_admin_session_lock(token, normalized)
        user = get_access_repository().get_user_by_email(normalized)
        if user is None:
            user = get_access_repository().create_email_user(normalized)
        if user is None:
            release_admin_session_lock(token)
            logout_admin()
            return None, "access.login_fail", None
        _set_registered_session(user)
        if remember_me:
            from worldcup_predictor.access.remember_login import (
                create_remember_token,
                persist_token_in_browser,
            )

            persist_token_in_browser(create_remember_token(user.user_id))
        st.session_state["gui_login_role"] = "admin"
        st.session_state["gui_mode"] = "developer"
        return user, None, "admin"

    if not verify_gui_password(pwd):
        return None, "access.login_fail", None

    user = get_access_repository().get_user_by_email(normalized)
    if user is None:
        user = get_access_repository().create_email_user(normalized)
    if user is None:
        return None, "access.login_fail", None

    _set_registered_session(user)
    st.session_state["gui_login_role"] = "user"
    logout_admin()
    if remember_me:
        from worldcup_predictor.access.remember_login import (
            create_remember_token,
            persist_token_in_browser,
        )

        persist_token_in_browser(create_remember_token(user.user_id))
    return user, None, "user"


def logout_gui() -> None:
    """Sign out user and release admin lock when applicable."""
    if is_admin_session():
        token = st.session_state.get("admin_session_token")
        if token:
            release_admin_session_lock(str(token))
        logout_admin()
    logout_user()
    st.session_state.pop("gui_login_role", None)


def current_login_role() -> LoginRole | None:
    init_access_session()
    role = st.session_state.get("gui_login_role")
    if role in {"admin", "user"}:
        return role  # type: ignore[return-value]
    if is_admin_session():
        return "admin"
    from worldcup_predictor.access.identity import is_registered_user

    if is_registered_user():
        return "user"
    return None
