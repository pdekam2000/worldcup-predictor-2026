"""Lineup Intelligence V2 UI — Phase 38."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.ui.gui_i18n import gui_t


def render_lineup_intelligence_v2(
    report: Any,
    locale: Locale,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> None:
    """Render Lineup Intelligence V2 card — never raises."""
    try:
        data = _resolve_lineup_data(report, specialist_report)
        if not data:
            return
        _render_card(data, report, locale)
    except Exception:
        st.caption(gui_t("lineup_v2.unavailable", locale))


def _resolve_lineup_data(
    report: Any,
    specialist_report: MatchSpecialistReport | None,
) -> dict[str, Any] | None:
    if specialist_report:
        sig = specialist_report.signal("lineup_intelligence_agent")
        if sig and sig.signals:
            return dict(sig.signals)
    if report is None:
        return None
    try:
        from worldcup_predictor.lineups.lineup_intelligence_engine import build_lineup_intelligence

        api_client = None
        try:
            from worldcup_predictor.config.settings import get_settings
            from worldcup_predictor.clients.api_football import ApiFootballClient

            settings = get_settings()
            if settings.api_football_configured:
                api_client = ApiFootballClient(settings)
        except Exception:
            pass
        return build_lineup_intelligence(report, api_client=api_client).to_dict()
    except Exception:
        return None


def _render_card(data: dict[str, Any], report: Any, locale: Locale) -> None:
    home = data.get("home") or {}
    away = data.get("away") or {}
    impact = data.get("prediction_impact") or {}

    home_name = getattr(getattr(report, "home_team", None), "team_name", "Home") if report else "Home"
    away_name = getattr(getattr(report, "away_team", None), "team_name", "Away") if report else "Away"

    with st.container(border=True):
        st.markdown(f"#### {gui_t('lineup_v2.title', locale)}")
        if data.get("summary"):
            st.caption(str(data["summary"]))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**{home_name}**")
            st.caption(_format_side_status(home, locale))
            st.metric(gui_t("lineup_v2.strength", locale), f"{home.get('lineup_strength', 0):.0f}/100")
            st.metric(gui_t("lineup_v2.confidence", locale), f"{home.get('confidence', 0):.0f}%")
        with c2:
            st.markdown(f"**{away_name}**")
            st.caption(_format_side_status(away, locale))
            st.metric(gui_t("lineup_v2.strength", locale), f"{away.get('lineup_strength', 0):.0f}/100")
            st.metric(gui_t("lineup_v2.confidence", locale), f"{away.get('confidence', 0):.0f}%")

        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.metric("Home XI", f"{home.get('starting_xi_count', 0)}/11")
        with d2:
            st.metric("Away XI", f"{away.get('starting_xi_count', 0)}/11")
        with d3:
            rot_h = home.get("rotation_count")
            rot_a = away.get("rotation_count")
            rot_label = "—"
            if rot_h is not None or rot_a is not None:
                rot_label = f"H {rot_h if rot_h is not None else '—'} / A {rot_a if rot_a is not None else '—'}"
            st.metric(gui_t("lineup_v2.rotations", locale), rot_label)
        with d4:
            gk_h = home.get("goalkeeper_status", "unknown")
            gk_a = away.get("goalkeeper_status", "unknown")
            st.metric(gui_t("lineup_v2.goalkeeper", locale), f"H:{gk_h} / A:{gk_a}")

        missing = list(dict.fromkeys((home.get("missing_key_players") or []) + (away.get("missing_key_players") or [])))
        if missing:
            st.markdown(f"**{gui_t('lineup_v2.missing_players', locale)}**")
            st.caption(", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))

        flags = sorted(set((home.get("risk_flags") or []) + (away.get("risk_flags") or [])))
        if flags:
            st.markdown(f"**{gui_t('lineup_v2.risk_flags', locale)}**")
            st.caption(" · ".join(flags))

        if any(impact.get(k) for k in ("home_adjustment", "away_adjustment", "over25_adjustment")):
            st.markdown(f"**{gui_t('lineup_v2.prediction_impact', locale)}**")
            st.caption(
                f"Home {impact.get('home_adjustment', 0):+.1f} · "
                f"Away {impact.get('away_adjustment', 0):+.1f} · "
                f"Over 2.5 {impact.get('over25_adjustment', 0):+.1f} · "
                f"Under 2.5 {impact.get('under25_adjustment', 0):+.1f}"
            )
        st.caption(gui_t("lineup_v2.disclaimer", locale))


def _format_side_status(side: dict[str, Any], locale: Locale) -> str:
    xi = side.get("starting_xi_count", 0)
    subs = side.get("substitutes_count", 0)
    form = side.get("formation") or "—"
    if side.get("official_lineup"):
        status = gui_t("lineup_v2.official", locale)
    elif side.get("lineup_available"):
        status = gui_t("lineup_v2.announced", locale)
    else:
        status = gui_t("lineup_v2.not_available", locale)
    return f"{status} · XI {xi} · Subs {subs} · {form}"
