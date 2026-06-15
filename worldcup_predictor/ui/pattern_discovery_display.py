"""GUI display for Pattern Discovery V2 — cards, tables, badges."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.learning.patterns.pattern_models import (
    DecisionAgentAdvice,
    DiscoveredPattern,
    PatternDiscoveryReport,
)
from worldcup_predictor.ui.gui_i18n import gui_t


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _confidence_badge(level: str) -> str:
    mapping = {
        "low": "🔴",
        "medium": "🟡",
        "high": "🟢",
    }
    return mapping.get(level, "⚪")


def _patterns_to_df(patterns: list[DiscoveredPattern]) -> pd.DataFrame:
    rows = []
    for p in patterns:
        rows.append(
            {
                "Pattern": p.label,
                "Winrate": _pct(p.winrate),
                "Baseline": _pct(p.baseline_winrate),
                "Sample": p.sample_size,
                "Confidence": f"{_confidence_badge(p.confidence_level)} {p.confidence_level.title()}",
                "Strength": f"{p.statistical_strength:.2f}",
                "Conditions": "; ".join(p.conditions),
            }
        )
    return pd.DataFrame(rows)


def _render_pattern_cards(patterns: list[DiscoveredPattern], locale: Locale) -> None:
    if not patterns:
        st.caption(gui_t("patterns.none", locale))
        return
    for p in patterns[:6]:
        badge = _confidence_badge(p.confidence_level)
        st.markdown(
            f'<div class="match-card" style="border-left-color: {"#22c55e" if p.kind == "success" else "#ef4444"};">'
            f'<div class="teams">{badge} {p.label}</div>'
            f'<div class="meta">'
            f'<span><label>{gui_t("patterns.winrate", locale)}</label><strong>{_pct(p.winrate)}</strong></span>'
            f'<span><label>{gui_t("patterns.sample", locale)}</label><strong>{p.sample_size}</strong></span>'
            f'<span><label>{gui_t("patterns.confidence", locale)}</label><strong>{p.confidence_level.title()}</strong></span>'
            f"</div></div>",
            unsafe_allow_html=True,
        )
        st.caption("; ".join(p.conditions))


def _render_advice(advice: list[DecisionAgentAdvice], locale: Locale) -> None:
    if not advice:
        st.caption(gui_t("patterns.no_advice", locale))
        return
    for item in advice:
        priority_color = {"high": "#ef4444", "medium": "#eab308", "low": "#94a3b8"}.get(
            item.priority, "#94a3b8"
        )
        st.markdown(
            f'<span class="status-pill" style="background:{priority_color}22;color:{priority_color};'
            f'border:1px solid {priority_color}55;">● {item.priority.upper()}</span> {item.message}',
            unsafe_allow_html=True,
        )


def render_pattern_discovery_panel(report: PatternDiscoveryReport, locale: Locale) -> None:
    """Render Learning Agent V2 pattern sections."""
    st.subheader(gui_t("patterns.title", locale))
    st.caption(
        f"{gui_t('patterns.baseline', locale)}: **{_pct(report.baseline_winrate)}** · "
        f"{gui_t('patterns.rows', locale)}: **{report.total_rows}**"
    )

    tab_strong, tab_weak, tab_fail, tab_success, tab_advice = st.tabs(
        [
            gui_t("patterns.strongest", locale),
            gui_t("patterns.weakest", locale),
            gui_t("patterns.failure_causes", locale),
            gui_t("patterns.success_causes", locale),
            gui_t("patterns.advice", locale),
        ]
    )

    with tab_strong:
        _render_pattern_cards(report.strongest_patterns, locale)
        df = _patterns_to_df(report.strongest_patterns)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_weak:
        _render_pattern_cards(report.weakest_patterns, locale)
        df = _patterns_to_df(report.weakest_patterns)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_fail:
        _render_pattern_cards(report.failure_causes, locale)
        df = _patterns_to_df(report.failure_causes)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_success:
        _render_pattern_cards(report.success_causes, locale)
        df = _patterns_to_df(report.success_causes)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_advice:
        _render_advice(report.decision_agent_advice, locale)

    if report.competition_patterns:
        st.markdown(f"**{gui_t('patterns.by_competition', locale)}**")
        comp_rows = []
        for comp, patterns in sorted(report.competition_patterns.items()):
            for p in patterns[:3]:
                comp_rows.append(
                    {
                        "Competition": comp,
                        "Pattern": p.label,
                        "Winrate": _pct(p.winrate),
                        "Sample": p.sample_size,
                        "Confidence": p.confidence_level.title(),
                    }
                )
        if comp_rows:
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
