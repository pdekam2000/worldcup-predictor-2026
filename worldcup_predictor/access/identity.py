"""Session user identity for public access — username/email + shared invite code."""

from __future__ import annotations

import hmac
import uuid

import streamlit as st

from worldcup_predictor.access.config import (
    credentials_login_available,
    public_access_code,
    public_access_enabled,
)
from worldcup_predictor.access.models import AppUser
from worldcup_predictor.access.repository import (
    AccessRepository,
    get_access_repository,
    normalize_user_identity,
)


def _repo() -> AccessRepository:
    return get_access_repository()


def _local_dev_bypass() -> bool:
    """Skip login when no credentials are configured."""
    return not credentials_login_available()


def init_access_session() -> None:
    """Ensure session keys exist — never raises."""
    if _local_dev_bypass():
        st.session_state.setdefault("access_user_id", "local_dev")
        return
    st.session_state.setdefault("anonymous_user_id", str(uuid.uuid4()))
    if not st.session_state.get("access_user_id"):
        from worldcup_predictor.access.remember_login import (
            inject_remember_restore_probe,
            try_restore_remembered_login,
        )

        inject_remember_restore_probe()
        try_restore_remembered_login()


def current_user_id() -> str:
    init_access_session()
    if _local_dev_bypass():
        return "local_dev"
    registered = st.session_state.get("access_user_id")
    if registered:
        return str(registered)
    anon = str(st.session_state.get("anonymous_user_id", uuid.uuid4()))
    user = _repo().get_or_create_anonymous_user(anon)
    if user:
        return user.user_id
    return f"anon_{anon}"


def current_user() -> AppUser | None:
    if _local_dev_bypass():
        return None
    uid = st.session_state.get("access_user_id")
    if not uid:
        anon = st.session_state.get("anonymous_user_id")
        if anon:
            return _repo().get_or_create_anonymous_user(str(anon))
        return None
    return _repo().get_user_by_id(str(uid))


def is_registered_user() -> bool:
    uid = st.session_state.get("access_user_id")
    if not uid or uid == "local_dev":
        return False
    return credentials_login_available()


def verify_invite_access_code(access_code: str) -> bool:
    """True when provided code matches configured PUBLIC_ACCESS_CODE."""
    expected = public_access_code()
    provided = (access_code or "").strip()
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _set_registered_session(user: AppUser) -> None:
    st.session_state["access_user_id"] = user.user_id
    st.session_state["access_user_email"] = user.email
    st.session_state.pop("anonymous_user_id", None)
    _repo().touch_login(user.user_id)


def login_with_invite(
    *,
    identity: str,
    access_code: str,
    email: str | None = None,
    remember_me: bool = False,
) -> tuple[AppUser | None, str | None]:
    """Sign in with username/email + shared PUBLIC_ACCESS_CODE.

    Returns (user, error_i18n_key). error is None on success.
    """
    raw_identity = identity if email is None else email
    normalized = normalize_user_identity(raw_identity or "")
    code = (access_code or "").strip()

    if not normalized:
        return None, "access.username_required"
    if not code:
        return None, "access.access_code_required"

    expected = public_access_code()
    if not expected:
        return None, "access.invite_not_configured"
    if not hmac.compare_digest(code, expected):
        return None, "access.invalid_access_code"

    user = _repo().get_user_by_email(normalized)
    if user is None:
        user = _repo().create_email_user(normalized)
    if user is None:
        return None, "access.login_fail"

    _set_registered_session(user)
    if remember_me:
        from worldcup_predictor.access.remember_login import (
            create_remember_token,
            persist_token_in_browser,
        )

        token = create_remember_token(user.user_id)
        persist_token_in_browser(token)
    return user, None


def logout_user() -> None:
    from worldcup_predictor.access.remember_login import clear_token_in_browser

    uid = st.session_state.get("access_user_id")
    if uid:
        get_access_repository().revoke_remember_tokens(str(uid))
    clear_token_in_browser()
    st.session_state.pop("access_user_id", None)
    st.session_state.pop("access_user_email", None)
    st.session_state["anonymous_user_id"] = str(uuid.uuid4())


def ensure_local_dev_user() -> None:
    """No-op placeholder for tests."""
    init_access_session()
