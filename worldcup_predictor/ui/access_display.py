"""Public access UI — login, quota messages, gate blocks."""

from __future__ import annotations

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


def render_access_sidebar(locale: Locale) -> None:
    """Email/token login in sidebar when public access is enabled."""
    if not public_access_enabled():
        return
    init_access_session()
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**{gui_t('access.account', locale)}**")
    user = current_user()
    quota = preview_prediction_quota()

    if user and user.email:
        st.sidebar.caption(f"{user.email}")
    elif user and user.is_anonymous:
        st.sidebar.caption(gui_t("access.anonymous", locale))

    if quota.is_paid:
        st.sidebar.success(gui_t("access.paid_active", locale))
    else:
        st.sidebar.caption(
            gui_t("access.quota_line", locale).format(
                used=quota.used_today,
                limit=quota.daily_limit,
                remaining=quota.remaining or 0,
            )
        )

    with st.sidebar.expander(gui_t("access.login_expand", locale), expanded=not is_registered_user()):
        with st.form("access_login_form"):
            email = st.text_input(gui_t("access.email", locale))
            token = st.text_input(gui_t("access.token", locale), type="password")
            login_btn = st.form_submit_button(gui_t("access.login", locale))
        if login_btn and token:
            if login_with_credentials(email=email or None, access_token=token):
                st.toast(gui_t("access.login_ok", locale))
                st.rerun()
            else:
                st.error(gui_t("access.login_fail", locale))

        with st.form("access_register_form"):
            reg_email = st.text_input(gui_t("access.register_email", locale), key="reg_email")
            reg_btn = st.form_submit_button(gui_t("access.register", locale))
        if reg_btn and reg_email:
            created = register_or_login_with_email(reg_email)
            if created:
                st.success(gui_t("access.token_created", locale))
                st.code(created.access_token, language=None)
                st.rerun()

    if is_registered_user() and st.sidebar.button(gui_t("access.logout", locale), key="access_logout"):
        logout_user()
        st.rerun()

    if admin_credentials_configured() and public_access_enabled():
        st.sidebar.markdown("---")
        if is_admin_session():
            st.sidebar.caption(gui_t("admin.signed_in", locale))
            if st.sidebar.button(gui_t("admin.logout", locale), key="admin_logout"):
                logout_admin()
                st.rerun()
        else:
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
    """Show upgrade / limit message when gate blocks."""
    if result.allowed:
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
    """Optional banner on predict page."""
    if not public_access_enabled():
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
