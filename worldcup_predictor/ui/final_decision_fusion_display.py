"""Final Decision Fusion V2 UI — Phase 46."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_final_decision_fusion_v2(
    prediction: MatchPrediction | None,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render fusion card — never raises."""
    try:
        data = _resolve_data(prediction, report, specialist_report)
        if not data:
            return
        _render_card(data, locale)
    except Exception:
        st.caption(gui_t("fusion_v2.unavailable", locale))


def _resolve_data(
    prediction: MatchPrediction | None,
    report: Any,
    specialist_report: MatchSpecialistReport | None,
) -> dict[str, Any] | None:
    if prediction is None:
        return None
    try:
        from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import (
            build_final_decision_fusion,
            load_fusion_from_prediction,
        )

        loaded = load_fusion_from_prediction(prediction)
        if loaded:
            return loaded.to_dict()
        return build_final_decision_fusion(
            prediction,
            report=report,
            specialist_report=specialist_report or getattr(report, "specialist_report", None),
        ).to_dict()
    except Exception:
        return None


def _render_card(data: dict[str, Any], locale: Locale) -> None:
    baseline = data.get("baseline_prediction") or {}
    fusion = data.get("fusion_prediction") or {}
    matrix = data.get("signal_matrix") or {}

    with st.container(border=True):
        st.markdown(f"#### {gui_t('fusion_v2.title', locale)}")
        if data.get("final_summary"):
            st.caption(str(data["final_summary"]))

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(gui_t("fusion_v2.consensus", locale), f"{data.get('consensus_strength', 0):.0f}/100")
        with c2:
            st.metric(gui_t("fusion_v2.quality", locale), data.get("decision_quality_band", "—"))
        with c3:
            st.metric(gui_t("fusion_v2.quality_score", locale), f"{data.get('decision_quality_score', 0):.0f}/100")
        with c4:
            st.metric(gui_t("fusion_v2.conf_adj", locale), f"{data.get('confidence_adjustment', 0):+.1f}")

        st.caption(
            f"**Baseline:** {baseline.get('one_x_two', '—')} · {baseline.get('over_under', '—')} · "
            f"conf {baseline.get('confidence_score', 0):.0f}"
        )
        st.caption(
            f"**Fusion:** {fusion.get('one_x_two', baseline.get('one_x_two', '—'))} · "
            f"{fusion.get('over_under', baseline.get('over_under', '—'))} · "
            f"conf {fusion.get('confidence_score', baseline.get('confidence_score', 0)):.0f}"
        )

        st.caption(
            f"**Signals:** Home {matrix.get('home_signal', 0):+.0f} · "
            f"Away {matrix.get('away_signal', 0):+.0f} · "
            f"Draw {matrix.get('draw_signal', 0):+.0f} · "
            f"O2.5 {matrix.get('over25_signal', 0):+.0f} · "
            f"U2.5 {matrix.get('under25_signal', 0):+.0f}"
        )

        agents = matrix.get("agents") or []
        if agents:
            top = sorted(agents, key=lambda a: abs(a.get("home_signal", 0)), reverse=True)[:4]
            st.caption(
                " · ".join(
                    f"{a.get('label', '?')}: H{a.get('home_signal', 0):+.0f}"
                    for a in top
                )
            )

        if data.get("conflict_resolution_summary"):
            st.caption(f"**Resolution:** {data['conflict_resolution_summary']}")

        conflicts = data.get("conflicts") or []
        if conflicts:
            st.markdown(f"**{gui_t('fusion_v2.conflicts', locale)}**")
            for c in conflicts[:4]:
                if isinstance(c, dict):
                    st.caption(f"• [{c.get('severity', 'medium')}] {c.get('description', '')}")

        flags = data.get("risk_flags") or []
        if flags:
            st.markdown(f"**{gui_t('fusion_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        st.caption(gui_t("fusion_v2.disclaimer", locale))
