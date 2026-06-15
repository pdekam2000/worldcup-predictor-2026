"""Prediction Explainability V2 UI — Phase 41."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.explainability.prediction_explainability_engine import build_prediction_explainability
from worldcup_predictor.ui.gui_i18n import gui_t


def render_prediction_explainability_v2(
    prediction: MatchPrediction | None,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render explainability card — never raises."""
    try:
        if prediction is None:
            return
        data = build_prediction_explainability(
            prediction,
            report,
            specialist_report=specialist_report or getattr(report, "specialist_report", None),
        ).to_dict()
        _render_card(data, locale)
    except Exception:
        st.caption(gui_t("explain_v2.unavailable", locale))


def _render_card(data: dict[str, Any], locale: Locale) -> None:
    with st.container(border=True):
        st.markdown(f"#### {gui_t('explain_v2.title', locale)}")
        if data.get("executive_summary"):
            st.markdown(str(data["executive_summary"]))

        fusion = data.get("fusion_report")
        if fusion:
            st.markdown(f"**{gui_t('fusion_v2.title', locale)}**")
            st.caption(
                f"Consensus {fusion.get('consensus_strength', 0):.0f}/100 · "
                f"Quality {fusion.get('decision_quality_band', '—')} · "
                f"Adj {fusion.get('confidence_adjustment', 0):+.1f}"
            )
            if fusion.get("final_summary"):
                st.caption(str(fusion["final_summary"]))

        conf = data.get("confidence") or {}
        agree = data.get("agreement") or {}
        conflicts = data.get("conflicts") or {}
        risk = data.get("risk_analysis") or {}

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(gui_t("explain_v2.confidence", locale), f"{conf.get('score', 0):.0f}/100")
        with c2:
            st.metric(gui_t("explain_v2.agreement", locale), f"{agree.get('agreement_score', 0):.0f}/100")
            st.caption(agree.get("agreement_band", "—"))
        with c3:
            st.metric(gui_t("explain_v2.conflicts", locale), f"{conflicts.get('conflict_score', 0):.0f}/100")
        with c4:
            st.metric(gui_t("explain_v2.risk", locale), risk.get("risk_level", "—"))

        if conf.get("boosters"):
            st.caption(f"**{gui_t('explain_v2.boosters', locale)}** — " + " · ".join(conf["boosters"][:5]))
        if conf.get("reducers"):
            st.caption(f"**{gui_t('explain_v2.reducers', locale)}** — " + " · ".join(conf["reducers"][:5]))

        contribs = data.get("agent_contributions") or []
        if contribs:
            st.markdown(f"**{gui_t('explain_v2.contributions', locale)}**")
            lines = [
                f"{c.get('label', '—')} … {c.get('raw_score', 0):+.0f} ({c.get('influence_pct', 0):.0f}%)"
                for c in contribs[:8]
            ]
            st.caption(" · ".join(lines))

        pos = data.get("top_positive_factors") or []
        neg = data.get("top_negative_factors") or []
        if pos or neg:
            p1, p2 = st.columns(2)
            with p1:
                if pos:
                    st.markdown(f"**{gui_t('explain_v2.top_positive', locale)}**")
                    st.caption(", ".join(pos))
            with p2:
                if neg:
                    st.markdown(f"**{gui_t('explain_v2.top_negative', locale)}**")
                    st.caption(", ".join(neg))

        timeline = data.get("decision_timeline") or []
        if timeline:
            st.markdown(f"**{gui_t('explain_v2.timeline', locale)}**")
            chain = " → ".join(f"{s.get('agent_label')}: {s.get('verdict')}" for s in timeline[:7])
            st.caption(chain)

        conflict_list = conflicts.get("conflicts") or []
        if conflict_list:
            st.markdown(f"**{gui_t('explain_v2.conflict_list', locale)}**")
            st.caption(" · ".join(conflict_list[:5]))

        risks = risk.get("top_risks") or []
        if risks:
            st.markdown(f"**{gui_t('explain_v2.top_risks', locale)}**")
            st.caption(" · ".join(risks[:5]))

        outcomes = data.get("outcome_explanations") or []
        if outcomes:
            st.markdown(f"**{gui_t('explain_v2.outcomes', locale)}**")
            for o in outcomes[:4]:
                st.caption(f"**{o.get('outcome', '—')}** — {o.get('explanation', '')}")

        st.caption(gui_t("explain_v2.disclaimer", locale))
