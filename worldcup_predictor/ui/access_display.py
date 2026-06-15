"""Public access UI — login, quota messages, gate blocks."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.access.admin_auth import (
    admin_credentials_configured,
    is_admin_session,
    login_admin,
    logout_admin,
)
from worldcup_predictor.access.config import (
    free_daily_prediction_limit,
    paid_unlock_price_eur,
    public_access_enabled,
)
from worldcup_predictor.access.identity import (
    current_user,
    init_access_session,
    is_registered_user,
    login_with_credentials,
    logout_user,
    register_or_login_with_email,
)
from worldcup_predictor.access.prediction_gate import GateCheckResult, preview_prediction_quota
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def access_ui_enabled() -> bool:
    return public_access_enabled()


def render_access_sidebar(locale: Locale) -> None:
    """Prominent account / login block at top of sidebar."""
    if not access_ui_enabled():
        return
    init_access_session()
    st.sidebar.markdown("---")
    _render_access_panel(st.sidebar, locale, key_prefix="sb")
    _render_admin_sidebar(locale)


def render_access_home_panel(locale: Locale) -> None:
    """Login prompt on Home when user is not signed in."""
    if not access_ui_enabled():
        return
    init_access_session()
    if is_registered_user():
        _render_logged_in_summary(st, locale, key_prefix="home")
        return
    st.markdown(f"### {gui_t('access.panel_title', locale)}")
    st.info(gui_t("access.panel_hint", locale))
    _render_access_panel(st, locale, key_prefix="home", show_border=True)


def _render_logged_in_summary(container: Any, locale: Locale, *, key_prefix: str) -> None:
    user = current_user()
    quota = preview_prediction_quota()
    email = (user.email if user and user.email else st.session_state.get("access_user_email")) or "—"
    with container.container(border=True):
        st.markdown(f"**{gui_t('access.signed_in_as', locale)}** {email}")
        if quota.is_paid:
            st.success(gui_t("access.paid_active", locale))
        else:
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
            email = (user.email if user and user.email else st.session_state.get("access_user_email")) or "—"
            st.caption(gui_t("access.signed_in_as", locale) + f" **{email}**")
            if quota.is_paid:
                st.success(gui_t("access.paid_active", locale))
            else:
                st.caption(
                    gui_t("access.quota_line", locale).format(
                        used=quota.used_today,
                        limit=quota.daily_limit,
                        remaining=quota.remaining or 0,
                    )
                )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(gui_t("nav.upgrade", locale), key=f"{key_prefix}_upgrade", use_container_width=True):
                    st.session_state["gui_page"] = "upgrade"
                    st.rerun()
            with c2:
                if st.button(gui_t("access.logout", locale), key=f"{key_prefix}_logout", use_container_width=True):
                    logout_user()
                    st.rerun()
            return

        st.caption(gui_t("access.panel_hint", locale))
        with st.form(f"{key_prefix}_access_login_form"):
            identity = st.text_input(gui_t("access.email_or_user", locale))
            token = st.text_input(gui_t("access.token", locale), type="password")
            login_btn = st.form_submit_button(gui_t("access.login", locale), type="primary", use_container_width=True)
        if login_btn:
            if not token.strip():
                st.warning(gui_t("access.token_required", locale))
            elif login_with_credentials(email=identity or None, access_token=token):
                st.toast(gui_t("access.login_ok", locale))
                st.rerun()
            else:
                st.error(gui_t("access.login_fail", locale))

        st.markdown(f"**{gui_t('access.new_user', locale)}**")
        with st.form(f"{key_prefix}_access_register_form"):
            reg_email = st.text_input(gui_t("access.register_email", locale), key=f"{key_prefix}_reg_email")
            reg_btn = st.form_submit_button(gui_t("access.register", locale), use_container_width=True)
        if reg_btn and reg_email.strip():
            created = register_or_login_with_email(reg_email.strip())
            if created:
                st.success(gui_t("access.token_created", locale))
                st.code(created.access_token, language=None)
                st.caption(gui_t("access.save_token", locale))
                st.rerun()


def _render_admin_sidebar(locale: Locale) -> None:
    if not admin_credentials_configured() or not access_ui_enabled():
        return
    if is_admin_session():
        with st.sidebar.expander(gui_t("admin.login_expand", locale), expanded=False):
            st.caption(gui_t("admin.signed_in", locale))
            if st.button(gui_t("admin.logout", locale), key="admin_logout"):
                logout_admin()
                st.rerun()
        return
    with st.sidebar.expander(gui_t("admin.login_expand", locale), expanded=False):
        with st.form("admin_login_form"):
            admin_user = st.text_input(gui_t("auth.username", locale), key="admin_login_user")
            admin_pass = st.text_input(gui_t("auth.password", locale), type="password", key="admin_login_pass")
            admin_btn = st.form_submit_button(gui_t("admin.login", locale))
        if admin_btn:
            if login_admin(admin_user, admin_pass):
                st.toast(gui_t("admin.login_ok", locale))
                st.rerun()
            else:
                st.error(gui_t("admin.login_fail", locale))


def render_gate_block(result: GateCheckResult, locale: Locale) -> None:
    """Show login, upgrade, or limit message when gate blocks."""
    if result.allowed:
        return
    if result.reason == "login_required":
        st.warning(gui_t("access.login_required", locale))
        st.caption(gui_t("access.panel_hint", locale))
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
