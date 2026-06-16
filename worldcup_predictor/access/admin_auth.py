"""Admin authentication for Developer Mode — Phase 49 security."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import streamlit as st

from worldcup_predictor.access.config import _env_or_secret, public_access_enabled
from worldcup_predictor.ui.app_shell import DEV_NAV_ITEMS, LEGACY_USER_NAV_ITEMS

_SESSION_ADMIN = "admin_authenticated"
_ADMIN_LOCK_TTL = timedelta(hours=12)

# Extra sidebar pages hidden/disabled for non-admin logged-in users
ADMIN_ONLY_NAV_KEYS: frozenset[str] = frozenset(
    {
        "professional_reports",
        "hall_of_fame",
        "settings",
        "admin_entitlements",
        "feedback_viewer",
        "favorites",
        "shortlist",
        "api",
        "accuracy",
        "learning",
        "learning_center_v2",
        "automation",
        "specialists",
        "report",
        "audit",
        "backtest",
    }
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def admin_username_normalized() -> str:
    raw = (_env_or_secret("ADMIN_USERNAME") or "admin").strip().lower()
    return raw or "admin"


def admin_credentials() -> tuple[str, str] | None:
    """ADMIN_USERNAME/PASSWORD, else APP_USERNAME/PASSWORD when APP_AUTH enabled."""
    admin_user = admin_username_normalized()
    admin_pass = (_env_or_secret("ADMIN_PASSWORD") or "").strip()
    if admin_pass:
        return admin_user, admin_pass
    if _truthy(_env_or_secret("APP_AUTH_ENABLED")):
        app_user = (_env_or_secret("APP_USERNAME") or "").strip()
        app_pass = (_env_or_secret("APP_PASSWORD") or "").strip()
        if app_user and app_pass:
            return app_user.lower(), app_pass
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
    clear_stale_admin_session_lock()


def is_admin_session() -> bool:
    """True when user may access Developer Mode and dev-only routes."""
    init_admin_session()
    if not admin_gate_active():
        return True
    active = bool(st.session_state.get(_SESSION_ADMIN))
    if active:
        token = st.session_state.get("admin_session_token")
        if token:
            refresh_admin_session_lock(str(token))
    return active


def is_admin_only_nav_page(page: str | None) -> bool:
    return (page or "home") in ADMIN_ONLY_NAV_KEYS


def verify_admin_credentials(username: str, password: str) -> bool:
    creds = admin_credentials()
    if creds is None:
        return False
    expected_user, expected_pass = creds
    user_ok = username.strip().lower() == expected_user.lower()
    if not user_ok:
        return False
    provided = password or ""
    return hmac.compare_digest(provided, expected_pass)


def _admin_lock_repo():
    from worldcup_predictor.access.repository import get_access_repository

    return get_access_repository()


def _parse_lock_time(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def try_acquire_admin_session_lock(token: str, label: str) -> bool:
    """Only one active admin session — same token may re-acquire; stale locks expire."""
    if not token:
        return False
    try:
        repo = _admin_lock_repo()
        row = repo.get_admin_session_lock()
        now = datetime.now(timezone.utc)
        if row:
            holder = str(row.get("holder_token") or "")
            locked_at = _parse_lock_time(str(row.get("locked_at") or ""))
            if holder and holder != token and locked_at:
                if now - locked_at < _ADMIN_LOCK_TTL:
                    return False
        repo.set_admin_session_lock(token, label, now.isoformat())
        return True
    except Exception:
        return True


def acquire_admin_session_lock(token: str, label: str) -> None:
    """Assign admin lock to this session — last successful admin login wins."""
    if not token:
        return
    try:
        now = datetime.now(timezone.utc)
        _admin_lock_repo().set_admin_session_lock(token, label, now.isoformat())
    except Exception:
        pass


def clear_stale_admin_session_lock() -> None:
    """Drop expired admin lock rows so a fresh login is not blocked."""
    try:
        row = _admin_lock_repo().get_admin_session_lock()
        if not row:
            return
        locked_at = _parse_lock_time(str(row.get("locked_at") or ""))
        if locked_at is None:
            return
        if datetime.now(timezone.utc) - locked_at >= _ADMIN_LOCK_TTL:
            _admin_lock_repo().force_clear_admin_session_lock()
    except Exception:
        pass


def refresh_admin_session_lock(token: str) -> None:
    if not token or not st.session_state.get(_SESSION_ADMIN):
        return
    try:
        row = _admin_lock_repo().get_admin_session_lock()
        if row and str(row.get("holder_token") or "") == token:
            _admin_lock_repo().set_admin_session_lock(
                token,
                str(row.get("holder_label") or "admin"),
                datetime.now(timezone.utc).isoformat(),
            )
    except Exception:
        pass


def release_admin_session_lock(token: str) -> None:
    if not token:
        return
    try:
        _admin_lock_repo().clear_admin_session_lock(token)
    except Exception:
        pass


def login_admin(username: str, password: str) -> bool:
    if verify_admin_credentials(username, password):
        st.session_state[_SESSION_ADMIN] = True
        return True
    return False


def logout_admin() -> None:
    token = st.session_state.get("admin_session_token")
    if token:
        release_admin_session_lock(str(token))
    st.session_state[_SESSION_ADMIN] = False
    st.session_state["gui_mode"] = "user"
    page = st.session_state.get("gui_page", "home")
    if is_developer_only_page(page):
        st.session_state["gui_page"] = "home"
    elif is_admin_only_nav_page(page):
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
    if is_developer_only_page(page) or is_admin_only_nav_page(page):
        st.session_state["gui_page"] = "home"


def block_developer_route(page: str, locale) -> bool:
    """Return True if route was blocked (caller should not render page)."""
    from worldcup_predictor.ui.gui_i18n import gui_t

    if not is_developer_only_page(page) and not is_admin_only_nav_page(page):
        return False
    if is_admin_session():
        return False
    st.warning(gui_t("admin.dev_required", locale))
    return True
