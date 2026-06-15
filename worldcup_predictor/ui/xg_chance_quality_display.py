"""xG & Chance Quality Intelligence V2 UI — Phase 45."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_xg_chance_quality_intelligence_v2(
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render xG & chance quality card — never raises."""
    try:
        data = _resolve_data(report, specialist_report)
        if not data:
            return
        _render_card(data, report, locale)
    except Exception:
        st.caption(gui_t("xg_v2.unavailable", locale))


def _resolve_data(report: Any, specialist_report: MatchSpecialistReport | None) -> dict[str, Any] | None:
    if specialist_report:
        sig = specialist_report.signal("xg_chance_quality_intelligence_agent")
        if sig and sig.signals:
            return dict(sig.signals)
    if report is None:
        return None
    try:
        from worldcup_predictor.chance_quality.xg_chance_quality_intelligence_engine import (
            build_xg_chance_quality_intelligence,
        )

        return build_xg_chance_quality_intelligence(report).to_dict()
    except Exception:
        return None


def _render_card(data: dict[str, Any], report: Any, locale: Locale) -> None:
    home = data.get("home") or {}
    away = data.get("away") or {}
    impact = data.get("prediction_impact") or {}
    advantage = data.get("chance_quality_advantage") or {}

    home_name = home.get("team_name") or (
        getattr(getattr(report, "home_team", None), "team_name", "Home") if report else "Home"
    )
    away_name = away.get("team_name") or (
        getattr(getattr(report, "away_team", None), "team_name", "Away") if report else "Away"
    )

    mode = data.get("data_mode", "unavailable")
    xg_label = gui_t("xg_v2.mode_xg", locale) if data.get("xg_available") else gui_t("xg_v2.mode_fallback", locale)
    if mode == "unavailable":
        xg_label = gui_t("xg_v2.mode_unavailable", locale)

    with st.container(border=True):
        st.markdown(f"#### {gui_t('xg_v2.title', locale)}")
        if data.get("summary"):
            st.caption(str(data["summary"]))
        st.caption(f"**{gui_t('xg_v2.data_mode', locale)}:** {xg_label}")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(gui_t("xg_v2.goals_pressure", locale), f"{data.get('goals_pressure_score', 50):.0f}/100")
        with c2:
            st.metric(gui_t("xg_v2.chance_edge", locale), f"{data.get('home_chance_edge', 0):+.0f}")
        with c3:
            st.metric(gui_t("xg_v2.advantage", locale), advantage.get("side", "balanced").title())

        st.caption(
            f"**{home_name}** — Attack {home.get('attack_chance_quality', 50):.0f} · "
            f"Prevention {home.get('defensive_chance_prevention', 50):.0f} · "
            f"Conv {home.get('conversion_label', '—')} ({home.get('conversion_efficiency', 0):.2f})"
            + (f" · xG {home.get('xg_per_match') or home.get('xg') or '—'}" if data.get("xg_available") else "")
        )
        st.caption(
            f"**{away_name}** — Attack {away.get('attack_chance_quality', 50):.0f} · "
            f"Prevention {away.get('defensive_chance_prevention', 50):.0f} · "
            f"Conv {away.get('conversion_label', '—')} ({away.get('conversion_efficiency', 0):.2f})"
            + (f" · xG {away.get('xg_per_match') or away.get('xg') or '—'}" if data.get("xg_available") else "")
        )

        if advantage.get("reason"):
            st.caption(advantage["reason"])

        flags = data.get("risk_flags") or []
        if flags:
            st.markdown(f"**{gui_t('xg_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        if any(impact.get(k) for k in ("home_adjustment", "away_adjustment", "over25_adjustment")):
            st.markdown(f"**{gui_t('xg_v2.prediction_impact', locale)}**")
            st.caption(
                f"Home {impact.get('home_adjustment', 0):+.1f} · "
                f"Away {impact.get('away_adjustment', 0):+.1f} · "
                f"Draw {impact.get('draw_adjustment', 0):+.1f} · "
                f"O2.5 {impact.get('over25_adjustment', 0):+.1f} · "
                f"U2.5 {impact.get('under25_adjustment', 0):+.1f}"
            )
        st.caption(gui_t("xg_v2.disclaimer", locale))
