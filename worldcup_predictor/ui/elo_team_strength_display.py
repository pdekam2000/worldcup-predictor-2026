"""ELO & Team Strength Intelligence V2 UI — Phase 44."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_elo_team_strength_intelligence_v2(
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render ELO & team strength card — never raises."""
    try:
        data = _resolve_data(report, specialist_report)
        if not data:
            return
        _render_card(data, report, locale)
    except Exception:
        st.caption(gui_t("elo_v2.unavailable", locale))


def _resolve_data(report: Any, specialist_report: MatchSpecialistReport | None) -> dict[str, Any] | None:
    if specialist_report:
        sig = specialist_report.signal("elo_team_strength_intelligence_agent")
        if sig and sig.signals:
            return dict(sig.signals)
    if report is None:
        return None
    try:
        from worldcup_predictor.strength.team_strength_intelligence_engine import (
            build_elo_team_strength_intelligence,
        )

        return build_elo_team_strength_intelligence(report).to_dict()
    except Exception:
        return None


def _form_caption(prefix: str, form: dict[str, Any]) -> str:
    if not form or not form.get("matches"):
        return f"{prefix}: —"
    return (
        f"{prefix}: {form.get('form_string', '—')} · "
        f"{form.get('wins', 0)}W-{form.get('draws', 0)}D-{form.get('losses', 0)}L · "
        f"GF {form.get('goals_for', 0)} GA {form.get('goals_against', 0)} · "
        f"PPG {form.get('points_per_match', 0):.2f}"
    )


def _render_card(data: dict[str, Any], report: Any, locale: Locale) -> None:
    home = data.get("home") or {}
    away = data.get("away") or {}
    impact = data.get("prediction_impact") or {}
    matchup = data.get("matchup_advantage") or {}

    home_name = home.get("team_name") or (
        getattr(getattr(report, "home_team", None), "team_name", "Home") if report else "Home"
    )
    away_name = away.get("team_name") or (
        getattr(getattr(report, "away_team", None), "team_name", "Away") if report else "Away"
    )

    with st.container(border=True):
        st.markdown(f"#### {gui_t('elo_v2.title', locale)}")
        if data.get("summary"):
            st.caption(str(data["summary"]))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(gui_t("elo_v2.home_elo", locale), f"{data.get('home_elo', 1500):.0f}")
        with c2:
            st.metric(gui_t("elo_v2.away_elo", locale), f"{data.get('away_elo', 1500):.0f}")
        with c3:
            st.metric(gui_t("elo_v2.elo_diff", locale), f"{data.get('elo_difference', 0):+.0f}")

        st.caption(
            f"**{gui_t('elo_v2.matchup', locale)}:** {matchup.get('side', 'balanced').title()} — "
            f"{matchup.get('reason', '')}"
        )

        st.caption(_form_caption(f"**{home_name}** L5", home.get("form_last_5") or {}))
        st.caption(_form_caption(f"**{home_name}** L10", home.get("form_last_10") or {}))
        st.caption(_form_caption(f"**{away_name}** L5", away.get("form_last_5") or {}))
        st.caption(_form_caption(f"**{away_name}** L10", away.get("form_last_10") or {}))

        c4, c5, c6 = st.columns(3)
        with c4:
            st.metric(gui_t("elo_v2.attack", locale), f"{home.get('attack_strength', 50):.0f} / {away.get('attack_strength', 50):.0f}")
        with c5:
            st.metric(gui_t("elo_v2.defense", locale), f"{home.get('defense_strength', 50):.0f} / {away.get('defense_strength', 50):.0f}")
        with c6:
            st.metric(
                gui_t("elo_v2.momentum", locale),
                f"{home.get('momentum_score', 0):+.0f} / {away.get('momentum_score', 0):+.0f}",
            )

        flags = data.get("risk_flags") or []
        if flags:
            st.markdown(f"**{gui_t('elo_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        if any(impact.get(k) for k in ("home_adjustment", "away_adjustment", "draw_adjustment", "over25_adjustment")):
            st.markdown(f"**{gui_t('elo_v2.prediction_impact', locale)}**")
            st.caption(
                f"Home {impact.get('home_adjustment', 0):+.1f} · "
                f"Away {impact.get('away_adjustment', 0):+.1f} · "
                f"Draw {impact.get('draw_adjustment', 0):+.1f} · "
                f"O2.5 {impact.get('over25_adjustment', 0):+.1f} · "
                f"U2.5 {impact.get('under25_adjustment', 0):+.1f}"
            )
        st.caption(gui_t("elo_v2.disclaimer", locale))
