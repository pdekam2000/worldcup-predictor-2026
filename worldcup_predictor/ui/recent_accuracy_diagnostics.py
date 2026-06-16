"""Developer-only Recent Accuracy Diagnostics panel."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def render_recent_accuracy_diagnostics(locale: Locale, *, center: Any, competition_key: str) -> None:
    """Recent hit rate, patterns, calibration — developer mode only."""
    st.markdown(f"### {gui_t('accuracy.recent_diagnostics', locale)}")
    try:
        from worldcup_predictor.accuracy.live_calibration import load_live_calibration_config
        from worldcup_predictor.accuracy.recent_error_audit import build_recent_error_audit
        from worldcup_predictor.accuracy.recalibration_engine import (
            RECALIBRATION_JSON,
            build_recalibration_from_audit,
        )

        fixtures = list(getattr(center, "finished", []) or [])
        audit = build_recent_error_audit(fixtures, competition_key=competition_key)
        rec = build_recalibration_from_audit(audit)
        live = load_live_calibration_config(reload=True)

        if not audit.sample_adequate:
            st.warning(gui_t("accuracy.sample_small", locale).format(n=audit.total_verified))

        c1, c2, c3, c4 = st.columns(4)
        w = audit.windows[0] if audit.windows else None
        with c1:
            st.metric(gui_t("accuracy.recent_hit_1x2", locale), _pct(w.one_x_two if w else None))
        with c2:
            st.metric(gui_t("accuracy.recent_hit_ou", locale), _pct(w.over_under if w else None))
        with c3:
            st.metric(gui_t("accuracy.recent_verified", locale), audit.total_verified)
        with c4:
            st.metric(
                gui_t("accuracy.conf_correction", locale),
                f"{live.confidence_correction_factor:.2f}" if live.active else "—",
            )

        if audit.bias.repeated_patterns:
            st.markdown(f"**{gui_t('accuracy.worst_patterns', locale)}**")
            for p in audit.bias.repeated_patterns:
                st.caption(f"• {p}")

        if audit.root_causes:
            with st.expander(gui_t("accuracy.root_causes", locale), expanded=False):
                for c in audit.root_causes:
                    st.markdown(f"- {c}")

        if rec.fixes_applied:
            st.markdown(f"**{gui_t('accuracy.recommended_fixes', locale)}**")
            for fix in rec.fixes_applied:
                st.caption(f"• {fix}")

        if audit.agent_attribution:
            rows = [
                {
                    "Agent": a.label,
                    "Supported wrong": a.supported_wrong,
                    "Warned correctly": a.warned_correctly,
                }
                for a in audit.agent_attribution
                if a.supported_wrong or a.warned_correctly
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if RECALIBRATION_JSON.is_file():
            st.caption(gui_t("accuracy.recalibration_path", locale))
    except Exception:
        st.caption(gui_t("accuracy.diagnostics_unavailable", locale))


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"
