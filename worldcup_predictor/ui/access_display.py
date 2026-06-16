"""Public access UI — unified login, quota messages, gate blocks."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.access.admin_auth import is_admin_session
from worldcup_predictor.access.config import (
    credentials_login_available,
    free_daily_prediction_limit,
    paid_unlock_price_eur,
    public_access_config_debug,
    public_access_enabled,
)
from worldcup_predictor.access.identity import (
    current_user,
    init_access_session,
    is_registered_user,
)
from worldcup_predictor.access.prediction_gate import GateCheckResult, preview_prediction_quota
from worldcup_predictor.access.unified_auth import current_login_role, login_gui, logout_gui
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def access_ui_enabled() -> bool:
    return credentials_login_available()


def render_access_sidebar(locale: Locale) -> None:
    """Single username + password login in sidebar."""
    if not access_ui_enabled():
        return
    init_access_session()
    _render_access_panel(st.sidebar, locale, key_prefix="sb")


def render_admin_bottom_sidebar(locale: Locale) -> None:
    """Legacy hook — unified login lives in render_access_sidebar."""
    return


def render_admin_config_debug() -> None:
    """Admin-only live config line for Streamlit Cloud diagnosis."""
    if not is_admin_session():
        return
    st.sidebar.caption(public_access_config_debug())


def render_public_sign_in_wall(locale: Locale) -> None:
    """Block protected page content until the user signs in."""
    if not access_ui_enabled() or is_registered_user():
        return
    render_login_required_hint(locale)


def render_login_required_hint(locale: Locale) -> None:
    """Single login lives in the sidebar — no duplicate form on main pages."""
    if not access_ui_enabled():
        return
    st.markdown(
        f"""
<div class="login-required-callout">
  <div class="login-required-title">{gui_t("access.login_required", locale)}</div>
  <div class="login-required-body">{gui_t("access.use_sidebar_login", locale)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_access_home_panel(locale: Locale) -> None:
    """Logged-in summary on home, or hint to use sidebar login."""
    if not access_ui_enabled():
        return
    init_access_session()
    if is_registered_user():
        _render_logged_in_summary(st, locale, key_prefix="home")
        return
    render_login_required_hint(locale)


def _render_logged_in_summary(container: Any, locale: Locale, *, key_prefix: str) -> None:
    user = current_user()
    quota = preview_prediction_quota()
    email = (user.email if user and user.email else st.session_state.get("access_user_email")) or "—"
    role = current_login_role()
    with container.container(border=True):
        st.markdown(f"**{gui_t('access.signed_in_as', locale)}** {email}")
        if role == "admin":
            st.success(gui_t("access.role_admin", locale))
        elif role == "user":
            st.caption(gui_t("access.role_user", locale))
        if quota.is_paid:
            st.success(gui_t("access.paid_active", locale))
        elif role != "admin":
            st.metric(
                gui_t("access.remaining_today", locale),
                quota.remaining if quota.remaining is not None else 0,
                f"{quota.used_today}/{quota.daily_limit} used",
            )
        if st.button(gui_t("nav.upgrade", locale), key=f"{key_prefix}_upgrade", use_container_width=True):
            st.session_state["gui_page"] = "upgrade"
            st.rerun()


def _render_access_panel(container: Any, locale: Locale, *, key_prefix: str, show_border: bool = True) -> None:
    user = current_user()
    quota = preview_prediction_quota()
    wrapper = container.container(border=True) if show_border else container

    with wrapper:
        st.markdown(f"**{gui_t('access.panel_title', locale)}**")

        if is_registered_user():
            display_name = (
                user.email if user and user.email else st.session_state.get("access_user_email")
            ) or "—"
            st.markdown(f"**{gui_t('access.signed_in_as', locale)}** {display_name}")
            role = current_login_role()
            if role == "admin":
                st.success(gui_t("access.role_admin", locale))
            else:
                st.caption(gui_t("access.role_user", locale))
            if quota.is_paid:
                st.success(gui_t("access.paid_active", locale))
            elif role != "admin":
                st.metric(
                    gui_t("access.remaining_today", locale),
                    quota.remaining if quota.remaining is not None else 0,
                    f"{quota.used_today}/{quota.daily_limit} used",
                )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(gui_t("nav.upgrade", locale), key=f"{key_prefix}_upgrade", use_container_width=True):
                    st.session_state["gui_page"] = "upgrade"
                    st.rerun()
            with c2:
                if st.button(gui_t("access.logout", locale), key=f"{key_prefix}_logout", use_container_width=True):
                    logout_gui()
                    st.rerun()
            return

        st.caption(gui_t("access.panel_hint_short", locale))
        st.markdown('<div class="sidebar-login-form">', unsafe_allow_html=True)
        with st.form(f"{key_prefix}_unified_login_form"):
            username = st.text_input(gui_t("auth.username", locale))
            password = st.text_input(gui_t("auth.password", locale), type="password")
            remember = st.checkbox(gui_t("access.remember_me", locale), value=False)
            login_btn = st.form_submit_button(gui_t("access.login", locale), type="primary", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        if login_btn:
            _, err, role = login_gui(username=username, password=password, remember_me=remember)
            if err is None:
                msg = gui_t("access.login_ok_admin", locale) if role == "admin" else gui_t("access.login_ok", locale)
                st.toast(msg)
                st.rerun()
            err_key = err or "access.login_fail"
            st.error(gui_t(err_key, locale))


def render_gate_block(result: GateCheckResult, locale: Locale) -> None:
    """Show login, upgrade, or limit message when gate blocks."""
    if result.allowed:
        return
    if result.reason == "login_required":
        render_login_required_hint(locale)
        return
    limit = result.daily_limit or free_daily_prediction_limit()
    st.error(
        gui_t("access.limit_reached", locale).format(
            limit=limit,
            used=result.used_today,
        )
    )
    st.info(gui_t("access.upgrade_hint", locale).format(price=f"{paid_unlock_price_eur():.0f}"))
    if st.button(gui_t("nav.upgrade", locale), key=f"gate_upgrade_{result.user_id}"):
        st.session_state["gui_page"] = "upgrade"
        st.rerun()


def render_quota_banner(locale: Locale) -> None:
    """Banner on predict page for logged-in free users."""
    if not access_ui_enabled() or not is_registered_user():
        return
    if is_admin_session():
        return
    quota = preview_prediction_quota()
    if quota.is_paid:
        return
    st.caption(
        gui_t("access.quota_banner", locale).format(
            used=quota.used_today,
            limit=quota.daily_limit,
            remaining=quota.remaining or 0,
        )
    )
