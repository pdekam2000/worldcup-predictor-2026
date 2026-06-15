"""Admin authentication for Developer Mode — Phase 49 security."""

from __future__ import annotations

import os

import streamlit as st

from worldcup_predictor.access.config import public_access_enabled
from worldcup_predictor.ui.app_shell import DEV_NAV_ITEMS, LEGACY_USER_NAV_ITEMS

_SESSION_ADMIN = "admin_authenticated"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def admin_credentials() -> tuple[str, str] | None:
    """ADMIN_USERNAME/PASSWORD, else APP_USERNAME/PASSWORD when APP_AUTH enabled."""
    admin_user = (os.getenv("ADMIN_USERNAME") or "").strip()
    admin_pass = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if admin_user and admin_pass:
        return admin_user, admin_pass
    if _truthy(os.getenv("APP_AUTH_ENABLED")):
        app_user = (os.getenv("APP_USERNAME") or "").strip()
        app_pass = (os.getenv("APP_PASSWORD") or "").strip()
        if app_user and app_pass:
            return app_user, app_pass
    return None


def admin_credentials_configured() -> bool:
    return admin_credentials() is not None


def admin_gate_active() -> bool:
    """When true, Developer Mode requires admin login."""
    if public_access_enabled():
        return True
    return admin_credentials_configured()


def init_admin_session() -> None:
    st.session_state.setdefault(_SESSION_ADMIN, False)


def is_admin_session() -> bool:
    """True when user may access Developer Mode and dev-only routes."""
    init_admin_session()
    if not admin_gate_active():
        return True
    return bool(st.session_state.get(_SESSION_ADMIN))


def verify_admin_credentials(username: str, password: str) -> bool:
    creds = admin_credentials()
    if creds is None:
        return False
    expected_user, expected_pass = creds
    return username.strip() == expected_user and password == expected_pass


def login_admin(username: str, password: str) -> bool:
    if verify_admin_credentials(username, password):
        st.session_state[_SESSION_ADMIN] = True
        return True
    return False


def logout_admin() -> None:
    st.session_state[_SESSION_ADMIN] = False
    st.session_state["gui_mode"] = "user"
    page = st.session_state.get("gui_page", "home")
    if is_developer_only_page(page):
        st.session_state["gui_page"] = "home"


def mark_admin_from_app_auth(username: str, password: str) -> None:
    """Site-wide APP_AUTH login also grants admin when credentials match."""
    if verify_admin_credentials(username, password):
        st.session_state[_SESSION_ADMIN] = True


def developer_only_page_keys() -> frozenset[str]:
    keys = {k for k, _, _ in DEV_NAV_ITEMS if k != "settings"}
    keys.update(k for k, _, _ in LEGACY_USER_NAV_ITEMS)
    keys.update({"admin_entitlements", "feedback_viewer"})
    return frozenset(keys)


def is_developer_only_page(page: str | None) -> bool:
    return (page or "home") in developer_only_page_keys()


def enforce_non_admin_restrictions() -> None:
    """Force User Mode and safe routes for non-admin sessions."""
    if is_admin_session():
        return
    if st.session_state.get("gui_mode") == "developer":
        st.session_state["gui_mode"] = "user"
    page = st.session_state.get("gui_page", "home")
    if is_developer_only_page(page):
        st.session_state["gui_page"] = "home"


def block_developer_route(page: str, locale) -> bool:
    """Return True if route was blocked (caller should not render page)."""
    from worldcup_predictor.ui.gui_i18n import gui_t

    if not is_developer_only_page(page):
        return False
    if is_admin_session():
        return False
    st.warning(gui_t("admin.dev_required", locale))
    return True
