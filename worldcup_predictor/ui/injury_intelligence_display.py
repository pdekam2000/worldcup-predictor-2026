"""Injury & Suspension Intelligence V2 UI — Phase 39."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_injury_intelligence_v2(
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render injury intelligence card — never raises."""
    try:
        data = _resolve_data(report, specialist_report)
        if not data:
            return
        _render_card(data, report, locale)
    except Exception:
        st.caption(gui_t("injury_v2.unavailable", locale))


def _resolve_data(report: Any, specialist_report: MatchSpecialistReport | None) -> dict[str, Any] | None:
    if specialist_report:
        sig = specialist_report.signal("injury_suspension_intelligence_agent")
        if sig and sig.signals:
            return dict(sig.signals)
    if report is None:
        return None
    try:
        from worldcup_predictor.injuries.injury_intelligence_engine import build_injury_intelligence

        return build_injury_intelligence(report).to_dict()
    except Exception:
        return None


def _render_card(data: dict[str, Any], report: Any, locale: Locale) -> None:
    home = data.get("home") or {}
    away = data.get("away") or {}
    impact = data.get("prediction_impact") or {}

    home_name = getattr(getattr(report, "home_team", None), "team_name", "Home") if report else "Home"
    away_name = getattr(getattr(report, "away_team", None), "team_name", "Away") if report else "Away"

    with st.container(border=True):
        st.markdown(f"#### {gui_t('injury_v2.title', locale)}")
        if data.get("summary"):
            st.caption(str(data["summary"]))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**{home_name}**")
            st.metric(gui_t("injury_v2.impact_score", locale), f"{home.get('injury_impact_score', 0):.0f}/100")
            st.caption(gui_t("injury_v2.band", locale).format(band=home.get("impact_band", "—")))
            st.metric(gui_t("injury_v2.confidence", locale), f"{home.get('confidence', 0):.0f}%")
        with c2:
            st.markdown(f"**{away_name}**")
            st.metric(gui_t("injury_v2.impact_score", locale), f"{away.get('injury_impact_score', 0):.0f}/100")
            st.caption(gui_t("injury_v2.band", locale).format(band=away.get("impact_band", "—")))
            st.metric(gui_t("injury_v2.confidence", locale), f"{away.get('confidence', 0):.0f}%")

        hl = home.get("position_losses") or {}
        al = away.get("position_losses") or {}
        st.caption(
            f"**{home_name}** — Def {hl.get('defensive_loss', 0):.0f} · "
            f"Mid {hl.get('midfield_loss', 0):.0f} · Att {hl.get('attacking_loss', 0):.0f} · "
            f"**{away_name}** — Def {al.get('defensive_loss', 0):.0f} · "
            f"Mid {al.get('midfield_loss', 0):.0f} · Att {al.get('attacking_loss', 0):.0f}"
        )

        unavailable = (home.get("unavailable_players") or []) + (away.get("unavailable_players") or [])
        if unavailable:
            st.markdown(f"**{gui_t('injury_v2.unavailable_players', locale)}**")
            names = [
                f"{p.get('name')} ({p.get('status')}, imp {p.get('importance_score', 0):.0f})"
                for p in unavailable[:8]
            ]
            st.caption(", ".join(names) + ("…" if len(unavailable) > 8 else ""))

        flags = sorted(set((home.get("risk_flags") or []) + (away.get("risk_flags") or [])))
        if flags:
            st.markdown(f"**{gui_t('injury_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        if any(impact.get(k) for k in ("home_adjustment", "away_adjustment", "over25_adjustment")):
            st.markdown(f"**{gui_t('injury_v2.prediction_impact', locale)}**")
            st.caption(
                f"Home {impact.get('home_adjustment', 0):+.1f} · "
                f"Away {impact.get('away_adjustment', 0):+.1f} · "
                f"Over 2.5 {impact.get('over25_adjustment', 0):+.1f} · "
                f"Under 2.5 {impact.get('under25_adjustment', 0):+.1f}"
            )
        st.caption(gui_t("injury_v2.disclaimer", locale))
