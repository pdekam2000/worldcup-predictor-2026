"""Professional Match Report Export V2 UI — Phase 47."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.export.match_report_collector import collect_match_report_bundle
from worldcup_predictor.export.professional_match_report_exporter_v2 import ProfessionalMatchReportExporterV2
from worldcup_predictor.ui.gui_i18n import gui_t


def render_match_report_export_v2(
    prediction: MatchPrediction | None,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
    settings: Any | None = None,
) -> None:
    """Compact export section — never raises."""
    try:
        if prediction is None:
            return
        _render_section(prediction, report, locale, specialist_report=specialist_report)
    except Exception:
        st.caption(gui_t("export_v2.unavailable", locale))


def _render_section(
    prediction: MatchPrediction,
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None,
) -> None:
    export_locale = locale if locale in {"en", "de", "fa"} else "en"
    specialist = specialist_report or getattr(report, "specialist_report", None)

    with st.container(border=True):
        st.markdown(f"#### {gui_t('export_v2.title', locale)}")
        st.caption(gui_t("export_v2.hint", locale))

        c1, c2, c3 = st.columns(3)
        with c1:
            md_btn = st.button(gui_t("export_v2.btn_md", locale), key=f"export_md_{prediction.fixture_id}")
        with c2:
            json_btn = st.button(gui_t("export_v2.btn_json", locale), key=f"export_json_{prediction.fixture_id}")
        with c3:
            sum_btn = st.button(gui_t("export_v2.btn_summary", locale), key=f"export_sum_{prediction.fixture_id}")

        if not (md_btn or json_btn or sum_btn):
            last = st.session_state.get(f"export_paths_{prediction.fixture_id}")
            if last:
                st.success(gui_t("export_v2.saved", locale).format(paths=last))
            return

        bundle = collect_match_report_bundle(
            prediction,
            report=report,
            specialist_report=specialist,
            locale=export_locale,  # type: ignore[arg-type]
        )
        exporter = ProfessionalMatchReportExporterV2()
        formats: tuple[str, ...] = ()
        if md_btn:
            formats = ("markdown",)
        elif json_btn:
            formats = ("json",)
        elif sum_btn:
            formats = ("summary",)

        result = exporter.export(bundle, formats=formats)  # type: ignore[arg-type]
        paths = ", ".join(result.paths) if result.paths else gui_t("export_v2.failed", locale)
        if result.errors:
            st.warning(" · ".join(result.errors))
        st.session_state[f"export_paths_{prediction.fixture_id}"] = paths
        st.success(gui_t("export_v2.saved", locale).format(paths=paths))
