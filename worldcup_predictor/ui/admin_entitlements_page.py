"""Developer admin — entitlements manager."""

from __future__ import annotations

import streamlit as st

from worldcup_predictor.access.models import utc_today
from worldcup_predictor.access.repository import AccessRepository
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def render_admin_entitlements_page(locale: Locale) -> None:
    """Search users, mark paid, revoke, view usage."""
    try:
        _render(locale)
    except Exception:
        st.error(gui_t("admin.unavailable", locale))


def _render(locale: Locale) -> None:
    repo = AccessRepository()
    st.caption(gui_t("admin.hint", locale))

    query = st.text_input(gui_t("admin.search", locale), key="admin_user_search")
    if query.strip():
        users = repo.search_users(query.strip())
    else:
        users = repo.search_users("@", limit=10) if False else []

    if query.strip():
        if not users:
            st.info(gui_t("admin.no_users", locale))
        for user in users:
            ent = repo.get_entitlement(user.user_id)
            used = repo.get_usage_count(user.user_id, utc_today())
            label = user.email or user.user_id
            with st.expander(f"{label} · paid={ent.paid} · today={used}", expanded=False):
                st.caption(f"ID: {user.user_id}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(gui_t("admin.mark_paid", locale), key=f"paid_{user.user_id}"):
                        repo.mark_paid(user.user_id, provider="admin_manual")
                        st.rerun()
                with c2:
                    if st.button(gui_t("admin.revoke_paid", locale), key=f"revoke_{user.user_id}"):
                        repo.revoke_paid(user.user_id)
                        st.rerun()
                ref = st.text_input(gui_t("upgrade.payment_ref", locale), key=f"ref_{user.user_id}")
                if st.button(gui_t("admin.mark_paid_ref", locale), key=f"paidref_{user.user_id}") and ref:
                    repo.mark_paid(user.user_id, provider="admin_manual", payment_reference=ref)
                    st.rerun()
