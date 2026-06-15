"""Session user identity for public access — email + access token."""

from __future__ import annotations

import secrets
import uuid

import streamlit as st

from worldcup_predictor.access.config import public_access_enabled
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


def register_or_login_with_email(email: str) -> AppUser | None:
    user = _repo().create_email_user(email)
    if user:
        st.session_state["access_user_id"] = user.user_id
        st.session_state["access_user_email"] = user.email
        st.session_state.pop("anonymous_user_id", None)
    return user


def login_with_credentials(*, email: str | None, access_token: str) -> AppUser | None:
    user = _repo().authenticate(email=email, access_token=access_token)
    if user:
        st.session_state["access_user_id"] = user.user_id
        st.session_state["access_user_email"] = user.email
        st.session_state.pop("anonymous_user_id", None)
    return user


def logout_user() -> None:
    st.session_state.pop("access_user_id", None)
    st.session_state.pop("access_user_email", None)
    st.session_state["anonymous_user_id"] = str(uuid.uuid4())


def ensure_local_dev_user() -> None:
    """No-op placeholder for tests."""
    init_access_session()
