"""Optional password gate for Streamlit GUI deployment."""

from __future__ import annotations

import os

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def auth_enabled() -> bool:
    return _truthy(os.getenv("APP_AUTH_ENABLED", "false"))


def _expected_credentials() -> tuple[str, str] | None:
    username = (os.getenv("APP_USERNAME") or "").strip()
    password = (os.getenv("APP_PASSWORD") or "").strip()
    if not username or not password:
        return None
    return username, password


def require_auth(locale: Locale) -> bool:
    """Return True when user may proceed (auth disabled or already signed in)."""
    if not auth_enabled():
        return True
    if st.session_state.get("app_authenticated"):
        return True

    creds = _expected_credentials()
    st.markdown(f"### 🔐 {gui_t('auth.title', locale)}")
    if creds is None:
        st.error(
            "APP_AUTH_ENABLED is true but APP_USERNAME / APP_PASSWORD are not set. "
            "Configure credentials in `.env.production`."
        )
        st.stop()
        return False

    expected_user, expected_pass = creds
    with st.form("app_login_form", clear_on_submit=False):
        st.caption(gui_t("auth.required", locale))
        username = st.text_input(gui_t("auth.username", locale))
        password = st.text_input(gui_t("auth.password", locale), type="password")
        submitted = st.form_submit_button(gui_t("auth.login", locale), type="primary")

    if submitted:
        if username == expected_user and password == expected_pass:
            st.session_state["app_authenticated"] = True
            try:
                from worldcup_predictor.access.admin_auth import mark_admin_from_app_auth

                mark_admin_from_app_auth(username, password)
            except Exception:
                pass
            st.rerun()
        st.error(gui_t("auth.failed", locale))

    st.stop()
    return False
