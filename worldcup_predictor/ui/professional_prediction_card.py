"""Phase 48 — Professional final prediction summary card."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.export.match_report_collector import collect_match_report_bundle
from worldcup_predictor.export.professional_match_report_exporter_v2 import ProfessionalMatchReportExporterV2
from worldcup_predictor.ui.first_goal_display import (
    render_first_goal_intelligence_expander,
    render_first_goal_pro_card_section,
    resolve_first_goal_v2,
)
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.status_badges import (
    confidence_band,
    decision_quality_display,
    render_status_badge,
    risk_display,
)


def _resolve_fusion(
    prediction: MatchPrediction,
    report: Any,
    specialist_report: MatchSpecialistReport | None,
) -> dict[str, Any] | None:
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


def render_professional_prediction_card(
    prediction: MatchPrediction,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Top summary card — never raises."""
    try:
        _render_card(prediction, report, locale, specialist_report=specialist_report)
    except Exception:
        st.caption(gui_t("pro_card.unavailable", locale))


def _render_card(
    prediction: MatchPrediction,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None,
) -> None:
    ou_label = (
        prediction.over_under.label.get(locale)
        if prediction.over_under.label
        else prediction.over_under.selection
    )
    x2_label = (
        prediction.one_x_two.label.get(locale)
        if prediction.one_x_two.label
        else prediction.one_x_two.selection
    )
    fusion = _resolve_fusion(prediction, report, specialist_report) or {}
    quality_band = decision_quality_display(
        fusion.get("decision_quality_band"),
        score=fusion.get("decision_quality_score"),
    )
    conf_band = confidence_band(prediction.confidence_score)
    risk_band = risk_display(prediction.risk_level)

    st.markdown(f"### {gui_t('pro_card.title', locale)}")
    with st.container(border=True):
        st.markdown(f"## {prediction.match_name}")
        gs = getattr(prediction, "group_context", None)
        if gs and isinstance(gs, dict) and gs.get("group"):
            st.caption(f"{gui_t('card.group', locale)}: {gs.get('group')}")

        c1, c2 = st.columns(2)
        with c1:
            st.metric(gui_t("pro_card.one_x_two", locale), x2_label)
        with c2:
            st.metric(gui_t("pro_card.over_under", locale), ou_label)

        b1, b2, b3 = st.columns(3)
        with b1:
            render_status_badge(conf_band, kind="confidence", locale=locale)
            st.caption(f"{prediction.confidence_score:.0f}/100")
        with b2:
            render_status_badge(quality_band, kind="quality", locale=locale)
        with b3:
            render_status_badge(risk_band, kind="risk", locale=locale)

        fg_v2 = resolve_first_goal_v2(prediction, report, specialist_report=specialist_report)
        render_first_goal_pro_card_section(prediction, fg_v2, locale)
        render_first_goal_intelligence_expander(fg_v2, locale, key_suffix=str(prediction.fixture_id))

        summary = fusion.get("final_summary") or fusion.get("summary")
        if summary:
            st.info(str(summary))
        elif prediction.reasons:
            first = prediction.reasons[0]
            desc = first.description.get(locale) if first.description else first.key
            st.caption(desc)

        export_col, _ = st.columns([1, 2])
        with export_col:
            if st.button(
                gui_t("pro_card.export", locale),
                type="primary",
                key=f"pro_card_export_{prediction.fixture_id}",
            ):
                _run_export(prediction, report, locale, specialist_report=specialist_report)

        last_paths = st.session_state.get(f"export_paths_{prediction.fixture_id}")
        if last_paths:
            st.success(gui_t("export_v2.saved", locale).format(paths=last_paths))
            st.session_state["gui_last_export_paths"] = last_paths
            st.session_state["gui_last_export_fixture_id"] = prediction.fixture_id


def _run_export(
    prediction: MatchPrediction,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None,
) -> None:
    export_locale = locale if locale in {"en", "de", "fa"} else "en"
    specialist = specialist_report or getattr(report, "specialist_report", None)
    bundle = collect_match_report_bundle(
        prediction,
        report=report,
        specialist_report=specialist,
        locale=export_locale,  # type: ignore[arg-type]
    )
    result = ProfessionalMatchReportExporterV2().export(bundle, formats=("markdown", "json", "summary"))
    paths = ", ".join(result.paths) if result.paths else gui_t("export_v2.failed", locale)
    if result.errors:
        st.warning(" · ".join(result.errors))
    st.session_state[f"export_paths_{prediction.fixture_id}"] = paths
    st.session_state["gui_last_export_paths"] = paths
    st.session_state["gui_last_export_fixture_id"] = prediction.fixture_id
