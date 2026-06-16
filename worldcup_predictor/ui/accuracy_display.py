"""Accuracy / winrate UI — User Mode card + Developer detailed table."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from worldcup_predictor.accuracy.dashboard_metrics import AccuracyDashboardSnapshot, PeriodAccuracy
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _load_dashboard(center: Any) -> AccuracyDashboardSnapshot:
    from worldcup_predictor.accuracy.dashboard_metrics import build_accuracy_dashboard

    fixtures = list(getattr(center, "finished", []) or []) + list(getattr(center, "live", []) or [])
    fixtures += list(getattr(center, "upcoming", []) or [])
    return build_accuracy_dashboard(fixtures)


def render_user_accuracy_card(locale: Locale, *, center: Any) -> None:
    """Compact winrate card for User Mode home — never raises."""
    try:
        dash = _load_dashboard(center)
        p = dash.all_time
        st.markdown(f'<div class="dash-section-title">📈 {gui_t("accuracy.user_card_title", locale)}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric(gui_t("accuracy.total_predictions", locale), p.total_predictions)
            with c2:
                st.metric(gui_t("accuracy.verified", locale), p.verified_predictions)
            with c3:
                st.metric(gui_t("accuracy.1x2", locale), _pct(p.rate_1x2()))
            with c4:
                st.metric(gui_t("accuracy.ou", locale), _pct(p.rate_ou()))
            c5, c6, c7 = st.columns(3)
            with c5:
                st.metric(gui_t("performance.scoreline", locale), _pct(p.rate_scoreline()))
            with c6:
                st.metric(gui_t("performance.first_goal", locale), _pct(p.rate_first_goal_team()))
            with c7:
                st.metric(gui_t("accuracy.last_30_1x2", locale), _pct(dash.last_30_days.rate_1x2()))
            st.caption(gui_t("accuracy.user_disclaimer", locale))
    except Exception:
        st.caption(gui_t("accuracy.unavailable", locale))


def render_developer_accuracy_table(locale: Locale, dash: AccuracyDashboardSnapshot) -> None:
    """Detailed calculation table for Developer Mode."""
    rows = [
        _row(locale, "accuracy.total_predictions", dash.all_time.total_predictions, dash.last_30_days.total_predictions, is_count=True),
        _row(locale, "accuracy.verified", dash.all_time.verified_predictions, dash.last_30_days.verified_predictions, is_count=True),
        _row(locale, "accuracy.1x2", dash.all_time.rate_1x2(), dash.last_30_days.rate_1x2()),
        _row(locale, "accuracy.ou", dash.all_time.rate_ou(), dash.last_30_days.rate_ou()),
        _row(locale, "performance.scoreline", dash.all_time.rate_scoreline(), dash.last_30_days.rate_scoreline()),
        _row(locale, "performance.first_goal", dash.all_time.rate_first_goal_team(), dash.last_30_days.rate_first_goal_team()),
        _row(locale, "accuracy.fg_minute", dash.all_time.rate_first_goal_minute(), dash.last_30_days.rate_first_goal_minute()),
        _row(locale, "accuracy.fg_scorer", dash.all_time.rate_first_goal_scorer(), dash.last_30_days.rate_first_goal_scorer()),
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    if dash.formula_notes:
        with st.expander(gui_t("accuracy.formula", locale), expanded=False):
            for note in dash.formula_notes:
                st.markdown(f"- {note}")
    if dash.verification_markets:
        st.markdown(f"**{gui_t('accuracy.verification_markets', locale)}**")
        vrows = [
            {
                "Market": m.market,
                "Evaluated": m.evaluated,
                "Correct": m.correct,
                "Winrate": _pct(m.rate),
            }
            for m in dash.verification_markets
        ]
        st.dataframe(pd.DataFrame(vrows), use_container_width=True, hide_index=True)


def _row(
    locale: Locale,
    label_key: str,
    all_val: Any,
    last30_val: Any,
    *,
    is_count: bool = False,
) -> dict[str, str]:
    fmt = (lambda v: str(v)) if is_count else _pct
    return {
        gui_t("accuracy.metric", locale): gui_t(label_key, locale),
        gui_t("accuracy.all_time", locale): fmt(all_val) if not is_count else str(all_val),
        gui_t("accuracy.last_30_days", locale): fmt(last30_val) if not is_count else str(last30_val),
    }
