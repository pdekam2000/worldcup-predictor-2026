"""Phase 48 — User Mode / Developer Mode navigation and preferences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.access.admin_auth import is_admin_session
from worldcup_predictor.ui.app_shell import (
    DEV_NAV_ITEMS,
    LEGACY_USER_NAV_ITEMS,
    USER_MODE_V2_NAV_ITEMS,
)
from worldcup_predictor.ui.gui_i18n import gui_t

GuiMode = Literal["user", "developer"]

_PREFS_PATH = Path("data/gui_preferences.json")
_HIDDEN_ACTION_PAGES = frozenset({"opening", "upcoming"})


def load_default_gui_mode() -> GuiMode:
    """Load persisted default mode — falls back to user."""
    try:
        if _PREFS_PATH.is_file():
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
            mode = str(data.get("default_gui_mode", "user")).lower()
            if mode in {"user", "developer"}:
                return mode  # type: ignore[return-value]
    except Exception:
        pass
    return "user"


def save_default_gui_mode(mode: GuiMode) -> None:
    """Persist default mode — never raises."""
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if _PREFS_PATH.is_file():
            existing = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        existing["default_gui_mode"] = mode
        _PREFS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass


def init_gui_mode_state() -> None:
    if not is_admin_session():
        st.session_state["gui_mode"] = "user"
        return
    if "gui_mode" not in st.session_state:
        st.session_state["gui_mode"] = load_default_gui_mode()


def is_developer_mode() -> bool:
    if not is_admin_session():
        return False
    init_gui_mode_state()
    return st.session_state.get("gui_mode") == "developer"


def section_expanded(*, developer_mode: bool | None = None) -> bool:
    """Technical expanders: collapsed in User Mode, open in Developer Mode."""
    if developer_mode is None:
        developer_mode = is_developer_mode()
    return bool(developer_mode)


def all_page_keys(
    user_nav: list[tuple[str, str, str]],
    dev_nav: list[tuple[str, str, str]],
    *,
    legacy_user_nav: list[tuple[str, str, str]] | None = None,
) -> list[str]:
    keys = [k for k, _, _ in user_nav]
    if legacy_user_nav:
        keys.extend(k for k, _, _ in legacy_user_nav)
    keys.extend(k for k, _, _ in dev_nav)
    keys.extend(["opening", "upcoming", "predict"])
    return list(dict.fromkeys(keys))


def pages_for_mode(*, developer_mode: bool) -> set[str]:
    """All routable page keys for the active interface mode."""
    user_keys = {k for k, _, _ in USER_MODE_V2_NAV_ITEMS}
    hidden = set(_HIDDEN_ACTION_PAGES)
    if developer_mode:
        legacy = {k for k, _, _ in LEGACY_USER_NAV_ITEMS}
        dev = {k for k, _, _ in DEV_NAV_ITEMS}
        return user_keys | legacy | dev | hidden
    return user_keys | hidden


def primary_nav_for_mode(*, developer_mode: bool) -> list[tuple[str, str, str]]:
    """Sidebar primary radio items for the active mode."""
    if developer_mode:
        return USER_MODE_V2_NAV_ITEMS + LEGACY_USER_NAV_ITEMS
    return list(USER_MODE_V2_NAV_ITEMS)


def dev_expander_nav_items() -> list[tuple[str, str, str]]:
    """Developer expander entries (settings lives in primary nav)."""
    return [item for item in DEV_NAV_ITEMS if item[0] != "settings"]


def normalize_gui_page(page: str | None, *, developer_mode: bool) -> str:
    """Reset invalid pages to Home for the active mode."""
    key = (page or "home").strip() or "home"
    allowed = pages_for_mode(developer_mode=developer_mode)
    if key in allowed:
        return key
    return "home"


def sync_primary_nav_widget(*, developer_mode: bool) -> None:
    """Keep radio widget valid without overriding an active dev-only route."""
    primary = primary_nav_for_mode(developer_mode=developer_mode)
    primary_keys = [k for k, _, _ in primary]
    current_page = st.session_state.get("gui_page", "home")
    widget_key = "sidebar_user_nav"
    if current_page in primary_keys:
        st.session_state[widget_key] = current_page
    elif st.session_state.get(widget_key) not in primary_keys:
        st.session_state[widget_key] = primary_keys[0]


def apply_primary_nav_selection() -> None:
    """Radio on_change — user picked a primary nav item."""
    picked = st.session_state.get("sidebar_user_nav", "home")
    st.session_state["gui_page"] = picked


def navigate_to_page(page_key: str, *, developer_mode: bool) -> None:
    """Set active route; sync primary radio when target is a primary item."""
    st.session_state["gui_page"] = page_key
    primary_keys = {k for k, _, _ in primary_nav_for_mode(developer_mode=developer_mode)}
    if page_key in primary_keys:
        st.session_state["sidebar_user_nav"] = page_key


def render_mode_toggle(locale: Locale) -> None:
    """Sidebar mode switch — admin only."""
    if not is_admin_session():
        return
    init_gui_mode_state()
    current = st.session_state.get("gui_mode", "user")
    options: list[GuiMode] = ["user", "developer"]
    labels = {
        "user": gui_t("mode.user", locale),
        "developer": gui_t("mode.developer", locale),
    }
    picked = st.sidebar.radio(
        gui_t("mode.label", locale),
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda k: labels[k],
        key="gui_mode_toggle",
    )
    if picked != current:
        st.session_state["gui_mode"] = picked
        st.session_state["gui_page"] = normalize_gui_page(
            st.session_state.get("gui_page"),
            developer_mode=(picked == "developer"),
        )
        sync_primary_nav_widget(developer_mode=(picked == "developer"))
        st.rerun()
