"""Upgrade / Freischalten page — Phase 49."""

from __future__ import annotations

import streamlit as st

from worldcup_predictor.access.config import (
    free_daily_prediction_limit,
    paid_unlock_price_eur,
    public_access_enabled,
    stripe_configured,
)
from worldcup_predictor.access.identity import current_user, current_user_id, init_access_session
from worldcup_predictor.access.prediction_gate import preview_prediction_quota
from worldcup_predictor.access.repository import AccessRepository
from worldcup_predictor.access.stripe_checkout import create_checkout_session, verify_checkout_session
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def _handle_payment_return(locale: Locale) -> None:
    params = st.query_params
    payment = params.get("payment")
    session_id = params.get("session_id")
    if payment == "success" and session_id:
        paid, ref = verify_checkout_session(str(session_id))
        if paid:
            AccessRepository().mark_paid(
                current_user_id(),
                provider="stripe",
                payment_reference=ref or str(session_id),
            )
            st.success(gui_t("upgrade.payment_success", locale))
            try:
                st.query_params.clear()
            except Exception:
                pass
        else:
            st.warning(gui_t("upgrade.payment_pending", locale))
    elif payment == "canceled":
        st.info(gui_t("upgrade.payment_canceled", locale))


def render_upgrade_page(locale: Locale) -> None:
    """Upgrade page — never raises."""
    try:
        _render(locale)
    except Exception:
        st.info(gui_t("upgrade.unavailable", locale))


def _render(locale: Locale) -> None:
    init_access_session()
    _handle_payment_return(locale)

    if not public_access_enabled():
        st.info(gui_t("upgrade.local_mode", locale))
        return

    quota = preview_prediction_quota()
    price = paid_unlock_price_eur()
    limit = free_daily_prediction_limit()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"### {gui_t('upgrade.free_plan', locale)}")
        st.markdown(gui_t("upgrade.free_desc", locale).format(limit=limit))
        st.metric(gui_t("access.used_today", locale), quota.used_today)
    with c2:
        st.markdown(f"### {gui_t('upgrade.paid_plan', locale)}")
        st.markdown(gui_t("upgrade.paid_desc", locale).format(price=f"{price:.0f}"))

    if quota.is_paid:
        st.success(gui_t("access.paid_active", locale))
        ent = AccessRepository().get_entitlement(current_user_id())
        if ent.paid_at:
            st.caption(f"{gui_t('upgrade.paid_at', locale)}: {ent.paid_at}")
        return

    user = current_user()
    if stripe_configured():
        result = create_checkout_session(user_id=current_user_id(), email=user.email if user else None)
        if result.ok and result.checkout_url:
            st.link_button(
                gui_t("upgrade.pay_button", locale).format(price=f"{price:.0f}"),
                result.checkout_url,
                type="primary",
            )
        elif result.error:
            st.caption(gui_t("upgrade.stripe_error", locale).format(error=result.error))
    else:
        st.warning(gui_t("upgrade.stripe_not_configured", locale))

    st.markdown("---")
    st.markdown(f"**{gui_t('upgrade.manual_verify', locale)}**")
    with st.form("manual_payment_verify"):
        ref = st.text_input(gui_t("upgrade.payment_ref", locale))
        submitted = st.form_submit_button(gui_t("upgrade.verify_ref", locale))
    if submitted and ref.strip():
        AccessRepository().mark_paid(
            current_user_id(),
            provider="manual",
            payment_reference=ref.strip(),
        )
        st.success(gui_t("upgrade.manual_granted", locale))
        st.rerun()

    st.caption(gui_t("upgrade.disclaimer", locale))
