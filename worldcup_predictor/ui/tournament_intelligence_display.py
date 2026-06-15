"""Tournament Intelligence V2 UI — Phase 43."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_tournament_intelligence_v2(
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render tournament intelligence card — never raises."""
    try:
        data = _resolve_data(report, specialist_report)
        if not data:
            return
        _render_card(data, report, locale)
    except Exception:
        st.caption(gui_t("tournament_v2.unavailable", locale))


def _resolve_data(report: Any, specialist_report: MatchSpecialistReport | None) -> dict[str, Any] | None:
    if specialist_report:
        sig = specialist_report.signal("tournament_intelligence_agent")
        if sig and sig.signals:
            return dict(sig.signals)
    if report is None:
        return None
    try:
        from worldcup_predictor.tournament.tournament_intelligence_engine import build_tournament_intelligence

        return build_tournament_intelligence(report).to_dict()
    except Exception:
        return None


def _render_card(data: dict[str, Any], report: Any, locale: Locale) -> None:
    home = data.get("home") or {}
    away = data.get("away") or {}
    impact = data.get("prediction_impact") or {}

    home_name = home.get("team_name") or (
        getattr(getattr(report, "home_team", None), "team_name", "Home") if report else "Home"
    )
    away_name = away.get("team_name") or (
        getattr(getattr(report, "away_team", None), "team_name", "Away") if report else "Away"
    )

    with st.container(border=True):
        st.markdown(f"#### {gui_t('tournament_v2.title', locale)}")
        if data.get("summary"):
            st.caption(str(data["summary"]))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(gui_t("tournament_v2.context", locale), data.get("match_context", "—"))
            st.caption(data.get("tournament_name", ""))
        with c2:
            st.metric(gui_t("tournament_v2.pressure", locale), f"{data.get('pressure_score', 0):.0f}/100")
            st.caption(gui_t("tournament_v2.rotation", locale).format(risk=data.get("rotation_risk", "—")))
        with c3:
            st.metric(
                gui_t("tournament_v2.competition", locale),
                data.get("competition_type", "—").title(),
            )

        st.caption(
            f"**{home_name}** — {home.get('qualification_status', '—').replace('_', ' ')} · "
            f"Qual {home.get('qualification_probability', 0):.0f}% · Elim risk {home.get('elimination_risk', 0):.0f}% · "
            f"Motivation {home.get('motivation_boost', 0):+.0f}"
        )
        st.caption(
            f"**{away_name}** — {away.get('qualification_status', '—').replace('_', ' ')} · "
            f"Qual {away.get('qualification_probability', 0):.0f}% · Elim risk {away.get('elimination_risk', 0):.0f}% · "
            f"Motivation {away.get('motivation_boost', 0):+.0f}"
        )

        flags = data.get("risk_flags") or []
        if flags:
            st.markdown(f"**{gui_t('tournament_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        if any(impact.get(k) for k in ("home_adjustment", "away_adjustment", "draw_adjustment")):
            st.markdown(f"**{gui_t('tournament_v2.prediction_impact', locale)}**")
            st.caption(
                f"Home {impact.get('home_adjustment', 0):+.1f} · "
                f"Away {impact.get('away_adjustment', 0):+.1f} · "
                f"Draw {impact.get('draw_adjustment', 0):+.1f}"
            )
        st.caption(gui_t("tournament_v2.disclaimer", locale))
