"""Phase 48 — Clean User Mode home dashboard."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.professional_reports_page import list_exported_reports


def render_user_home_dashboard(
    locale: Locale,
    *,
    center: Any,
    api_ready: bool,
    last_prediction: Any | None,
    on_quick_predict: Callable[[], None] | None = None,
    goto_predict: Callable[[], None] | None = None,
) -> None:
    """Simple product dashboard — never raises."""
    try:
        _render(locale, center, api_ready, last_prediction, on_quick_predict, goto_predict)
    except Exception:
        st.info(gui_t("home.user_welcome", locale))


def _render(
    locale: Locale,
    center: Any,
    api_ready: bool,
    last_prediction: Any | None,
    on_quick_predict: Callable[[], None] | None,
    goto_predict: Callable[[], None] | None,
) -> None:
    st.markdown(f"### {gui_t('home.user_welcome', locale)}")
    st.caption(gui_t("home.user_subtitle", locale))

    st.markdown(f"#### {gui_t('home.next_fixtures', locale)}")
    upcoming = getattr(center, "upcoming", None) or []
    if upcoming:
        from worldcup_predictor.ui.gui_components import render_match_card as _render_match_card

        for fixture in upcoming[:4]:
            _render_match_card(fixture, locale, source=getattr(fixture, "source", None))
    else:
        st.info(gui_t("no_fixture", locale))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**{gui_t('home.last_prediction', locale)}**")
        if last_prediction and getattr(last_prediction, "success", False):
            pred = last_prediction.prediction
            st.metric(pred.match_name, f"{pred.one_x_two.selection} · {pred.over_under.selection}")
            st.caption(f"{gui_t('badge.confidence', locale)}: {pred.confidence_score:.0f}/100")
        else:
            st.caption(gui_t("home.no_prediction_yet", locale))

    with c2:
        st.markdown(f"**{gui_t('home.last_export', locale)}**")
        paths = st.session_state.get("gui_last_export_paths")
        fid = st.session_state.get("gui_last_export_fixture_id")
        if paths:
            st.caption(f"Fixture {fid}")
            st.code(str(paths)[:200], language=None)
        else:
            recent = list_exported_reports(limit=1)
            if recent:
                item = recent[0]
                st.caption(f"Fixture {item.fixture_id} · {item.created_utc}")
                path = item.summary_path or item.md_path or "—"
                st.code(str(path)[:200], language=None)
            else:
                st.caption(gui_t("home.no_export_yet", locale))

    with c3:
        st.markdown(f"**{gui_t('home.system_status', locale)}**")
        status_label = gui_t("home.status_ready", locale) if api_ready else gui_t("home.status_partial", locale)
        color = "#22c55e" if api_ready else "#f59e0b"
        st.markdown(
            f'<span class="status-pill" style="background:{color}22;color:{color};'
            f'border:1px solid {color}55;">● {status_label}</span>',
            unsafe_allow_html=True,
        )
        live = getattr(center, "live_count", 0)
        up = getattr(center, "upcoming_today_count", 0)
        st.caption(f"{gui_t('overview.live', locale)}: {live} · {gui_t('overview.upcoming_today', locale)}: {up}")

    st.markdown("---")
    action_col1, action_col2 = st.columns([1, 3])
    with action_col1:
        if st.button(gui_t("home.quick_predict", locale), type="primary", use_container_width=True):
            if goto_predict:
                goto_predict()
            elif on_quick_predict:
                on_quick_predict()
            else:
                st.session_state["gui_page"] = "predict"
                st.rerun()
