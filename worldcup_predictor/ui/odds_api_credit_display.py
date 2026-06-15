"""The Odds API credit usage panel — Phase 50A."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.access.admin_auth import is_admin_session
from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.providers.odds_api_credit import usage_summary
from worldcup_predictor.ui.gui_i18n import gui_t


def _guard_meta(intel: Any | None) -> dict[str, Any]:
    if intel is None:
        return {}
    meta = getattr(intel, "provider_metadata", None) or {}
    block = meta.get("odds_api_guard")
    return block if isinstance(block, dict) else {}


def _status_label(reason: str, locale: Locale) -> str:
    key = f"odds_api.status.{reason.split(':')[0]}"
    text = gui_t(key, locale)
    if text != key:
        return text
    if reason.startswith("cache_hit"):
        return gui_t("odds_api.status.cache_hit", locale)
    return reason.replace("_", " ").title()


def render_odds_api_credit_panel(
    locale: Locale,
    *,
    fixture_id: int | None = None,
    intel: Any | None = None,
    developer_mode: bool = False,
) -> None:
    """Show Odds API quota and last action; admin-only manual refresh."""
    settings = get_settings()
    summary = usage_summary(settings)
    guard = _guard_meta(intel)

    with st.container(border=True):
        st.markdown(f"**{gui_t('odds_api.panel_title', locale)}**")
        if not settings.the_odds_api_configured:
            st.caption(gui_t("odds_api.not_configured", locale))
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(
                gui_t("odds_api.used_today", locale),
                summary["daily_used"],
                f"/ {summary['daily_hard_limit']} hard",
            )
        with c2:
            st.metric(
                gui_t("odds_api.used_month", locale),
                summary["monthly_used"],
                f"/ {summary['monthly_limit']}",
            )
        with c3:
            st.metric(
                gui_t("odds_api.remaining_month", locale),
                summary["monthly_remaining"],
            )

        if guard:
            reason = str(guard.get("reason", ""))
            if guard.get("used_live"):
                st.success(gui_t("odds_api.last_used", locale))
            elif guard.get("from_cache"):
                st.info(gui_t("odds_api.last_cache", locale))
            elif reason:
                st.caption(
                    gui_t("odds_api.last_skipped", locale).format(status=_status_label(reason, locale))
                )

        if developer_mode and is_admin_session() and fixture_id:
            if st.button(gui_t("odds_api.refresh_btn", locale), key=f"odds_api_refresh_{fixture_id}"):
                st.session_state["odds_api_force_refresh_id"] = int(fixture_id)
                st.session_state.pop("gui_intelligence_cache", None)
                st.session_state.pop("match_center_action_cache", None)
                st.toast(gui_t("odds_api.refresh_toast", locale))
                st.rerun()
