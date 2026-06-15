"""Session user identity for public access — email + shared invite code."""

from __future__ import annotations

import hmac
import uuid

import streamlit as st

from worldcup_predictor.access.config import public_access_code, public_access_enabled
from worldcup_predictor.access.models import AppUser
from worldcup_predictor.access.repository import AccessRepository, get_access_repository


def _repo() -> AccessRepository:
    return get_access_repository()


def init_access_session() -> None:
    """Ensure session keys exist — never raises."""
    if not public_access_enabled():
        st.session_state.setdefault("access_user_id", "local_dev")
        return
    st.session_state.setdefault("anonymous_user_id", str(uuid.uuid4()))


def current_user_id() -> str:
    init_access_session()
    if not public_access_enabled():
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
    if not public_access_enabled():
        return None
    uid = st.session_state.get("access_user_id")
    if not uid:
        anon = st.session_state.get("anonymous_user_id")
        if anon:
            return _repo().get_or_create_anonymous_user(str(anon))
        return None
    return _repo().get_user_by_id(str(uid))


def is_registered_user() -> bool:
    return bool(st.session_state.get("access_user_id")) and public_access_enabled()


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


def login_with_invite(*, email: str, access_code: str) -> tuple[AppUser | None, str | None]:
    """Sign in with email + shared invite code.

    Returns (user, error_i18n_key). error is None on success.
    """
    normalized = (email or "").strip().lower()
    code = (access_code or "").strip()

    if not normalized or "@" not in normalized:
        return None, "access.email_required"
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
    return user, None


def logout_user() -> None:
    st.session_state.pop("access_user_id", None)
    st.session_state.pop("access_user_email", None)
    st.session_state["anonymous_user_id"] = str(uuid.uuid4())


def ensure_local_dev_user() -> None:
    """No-op placeholder for tests."""
    init_access_session()
