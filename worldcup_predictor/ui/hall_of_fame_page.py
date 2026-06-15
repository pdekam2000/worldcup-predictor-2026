"""Prediction Accuracy Hall of Fame — user-facing trust page (read-only)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.performance.hall_of_fame import (
    HallOfFameReport,
    HallOfFameWindow,
    build_hall_of_fame_report,
)
from worldcup_predictor.ui.gui_i18n import gui_t


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _render_window_block(window: HallOfFameWindow, locale: Locale, *, title_key: str) -> None:
    st.markdown(f"**{gui_t(title_key, locale)}**")
    if window.verified == 0:
        st.caption(gui_t("hall_of_fame.no_samples", locale))
        return
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric(gui_t("hall_of_fame.verified", locale), window.verified)
    with c2:
        st.metric(gui_t("accuracy.1x2", locale), _pct(window.one_x_two_accuracy))
    with c3:
        st.metric(gui_t("accuracy.ou", locale), _pct(window.over_under_accuracy))
    with c4:
        st.metric(gui_t("hall_of_fame.draw", locale), _pct(window.draw_accuracy))
    with c5:
        st.metric(gui_t("performance.grade", locale), window.model_grade)


def render_hall_of_fame_page(locale: Locale, *, competition_key: str | None = None) -> None:
    """Read-only trust dashboard — never raises."""
    try:
        report = build_hall_of_fame_report(competition_key=competition_key)
        _render(report, locale)
    except Exception:
        st.info(gui_t("hall_of_fame.unavailable", locale))


def _render(report: HallOfFameReport, locale: Locale) -> None:
    st.caption(report.disclaimer)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(gui_t("performance.total_predictions", locale), report.total_predictions)
    with c2:
        st.metric(gui_t("hall_of_fame.verified_total", locale), report.verified_predictions)
    with c3:
        st.metric(gui_t("performance.pending", locale), report.pending_predictions)

    st.markdown("---")
    _render_window_block(report.all_time, locale, title_key="hall_of_fame.all_time")
    st.markdown("---")
    _render_window_block(report.last_30_days, locale, title_key="hall_of_fame.last_30_days")
    st.markdown("---")
    _render_window_block(report.last_100, locale, title_key="hall_of_fame.last_100")

    if report.calibration_buckets:
        st.markdown(f"### {gui_t('hall_of_fame.calibration', locale)}")
        st.caption(gui_t("hall_of_fame.calibration_hint", locale))
        rows = [
            {
                gui_t("hall_of_fame.bucket", locale): bucket.label,
                gui_t("hall_of_fame.avg_confidence", locale): f"{bucket.predicted_confidence_avg:.0f}%",
                gui_t("hall_of_fame.hit_rate", locale): (
                    _pct(bucket.actual_hit_rate) if bucket.actual_hit_rate is not None else "—"
                ),
                gui_t("hall_of_fame.gap", locale): (
                    f"{bucket.calibration_gap * 100:+.1f}%" if bucket.calibration_gap is not None else "—"
                ),
                gui_t("hall_of_fame.count", locale): bucket.count,
            }
            for bucket in report.calibration_buckets
            if bucket.count > 0
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if report.best_tournaments:
        st.markdown(f"### {gui_t('hall_of_fame.best_tournaments', locale)}")
        trows = [
            {
                gui_t("hall_of_fame.tournament", locale): item.label,
                "1X2": _pct(item.one_x_two_accuracy),
                "O/U": _pct(item.over_under_accuracy),
                gui_t("hall_of_fame.draw", locale): _pct(item.draw_accuracy),
                gui_t("hall_of_fame.reliability", locale): f"{item.league_reliability_score:.0f}/100",
                gui_t("hall_of_fame.samples", locale): item.samples,
            }
            for item in report.best_tournaments
        ]
        st.dataframe(pd.DataFrame(trows), use_container_width=True, hide_index=True)

    if report.best_agents:
        st.markdown(f"### {gui_t('hall_of_fame.best_agents', locale)}")
        arows = [
            {
                gui_t("hall_of_fame.agent", locale): agent.label,
                gui_t("accuracy.1x2", locale): _pct(agent.accuracy),
                gui_t("hall_of_fame.reliability", locale): f"{agent.agent_reliability_score:.0f}/100",
                gui_t("hall_of_fame.contribution", locale): f"{agent.contribution_score:.0f}",
                gui_t("hall_of_fame.samples", locale): agent.samples,
            }
            for agent in report.best_agents
        ]
        st.dataframe(pd.DataFrame(arows), use_container_width=True, hide_index=True)

    if report.data_limitations:
        st.markdown(f"**{gui_t('hall_of_fame.limitations', locale)}**")
        for item in report.data_limitations:
            st.caption(f"• {item}")
