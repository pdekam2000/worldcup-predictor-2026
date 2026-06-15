"""Learning & Accuracy Center V2 UI — Phase 42."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.learning.self_learning_engine_v2 import build_self_learning_report
from worldcup_predictor.ui.gui_i18n import gui_t


def render_learning_accuracy_center_v2(locale: Locale, *, competition_key: str | None = None) -> None:
    """Render self-learning center — never raises."""
    try:
        report = build_self_learning_report(competition_key=competition_key)
        _render(report, locale)
    except Exception:
        st.info(gui_t("learning_v2.unavailable", locale))


def _render(report: Any, locale: Locale) -> None:
    st.markdown(f"### {gui_t('learning_v2.title', locale)}")
    st.caption(report.disclaimer)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(gui_t("learning_v2.total_records", locale), report.total_records)
    with c2:
        st.metric(gui_t("learning_v2.verified", locale), report.verified_records)
    with c3:
        st.metric(gui_t("learning_v2.pending", locale), report.pending_records)

    if report.insights:
        st.markdown(f"**{gui_t('learning_v2.insights', locale)}**")
        for item in report.insights:
            st.markdown(f"- {item}")

    if report.agent_rankings:
        st.markdown(f"**{gui_t('learning_v2.agent_rankings', locale)}**")
        rows = [
            {
                "Agent": a.label,
                "Reliability": f"{a.agent_reliability_score:.0f}",
                "Accuracy": f"{a.accuracy * 100:.1f}%" if a.accuracy is not None else "—",
                "Samples": a.samples,
                "Contribution": f"{a.contribution_score:.0f}",
            }
            for a in report.agent_rankings[:12]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if report.league_rankings:
        st.markdown(f"**{gui_t('learning_v2.league_rankings', locale)}**")
        lrows = [
            {
                "League": l.label,
                "Reliability": f"{l.league_reliability_score:.0f}",
                "1X2": f"{l.one_x_two_accuracy * 100:.1f}%" if l.one_x_two_accuracy is not None else "—",
                "O/U": f"{l.over_under_accuracy * 100:.1f}%" if l.over_under_accuracy is not None else "—",
                "Samples": l.samples,
            }
            for l in report.league_rankings[:8]
        ]
        st.dataframe(pd.DataFrame(lrows), use_container_width=True, hide_index=True)

    if report.calibration_buckets:
        st.markdown(f"**{gui_t('learning_v2.calibration', locale)}**")
        crows = [
            {
                "Bucket": b.label,
                "Avg confidence": f"{b.predicted_confidence_avg:.0f}%",
                "Hit rate": f"{b.actual_hit_rate * 100:.1f}%" if b.actual_hit_rate is not None else "—",
                "Gap": f"{b.calibration_gap * 100:+.1f}%" if b.calibration_gap is not None else "—",
                "Count": b.count,
            }
            for b in report.calibration_buckets
        ]
        st.dataframe(pd.DataFrame(crows), use_container_width=True, hide_index=True)

    if report.market_type_metrics:
        st.markdown(f"**{gui_t('learning_v2.market_types', locale)}**")
        mrows = [
            {
                "Market": m.label,
                "Accuracy": f"{m.accuracy * 100:.1f}%" if m.accuracy is not None else "—",
                "Samples": m.samples,
                "Avg conf.": f"{m.average_confidence:.0f}",
            }
            for m in report.market_type_metrics
        ]
        st.dataframe(pd.DataFrame(mrows), use_container_width=True, hide_index=True)

    if report.recommendations:
        st.markdown(f"**{gui_t('learning_v2.recommendations', locale)}**")
        st.warning(gui_t("learning_v2.human_review", locale))
        for rec in report.recommendations:
            st.markdown(f"- [{rec.priority.upper()}] {rec.message}")

    if report.prediction_history_sample:
        with st.expander(gui_t("learning_v2.history", locale)):
            st.dataframe(pd.DataFrame(report.prediction_history_sample), use_container_width=True, hide_index=True)
