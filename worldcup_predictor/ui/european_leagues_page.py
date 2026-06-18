"""Phase 39E — European Leagues Dashboard."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Locale, Settings
from worldcup_predictor.schedule.competition_schedule import build_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center
from worldcup_predictor.ui.competition_selector import competition_season
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.match_action_panel import render_match_action_panel


def render_european_leagues_dashboard(
    locale: Locale,
    settings: Settings,
    *,
    competition_key: str,
) -> None:
    comp = get_competition(competition_key)
    season = competition_season() or comp.season
    st.markdown(
        f'<div class="page-header"><h1>{gui_t("nav.european_leagues", locale)}</h1>'
        f'<p>{comp.display_name} · {gui_t("competition.season", locale)} {season}</p></div>',
        unsafe_allow_html=True,
    )

    try:
        service = build_schedule_service(settings, competition_key=competition_key, season=season)
        snapshot = build_match_center(service, settings, enrich_live=False, enrich_finished_limit=50)
    except Exception as exc:
        st.warning(gui_t("european.schedule_unavailable", locale))
        st.caption(str(exc))
        return

    cols = st.columns(3)
    with cols[0]:
        st.metric(gui_t("match_center.upcoming", locale), len(snapshot.upcoming))
    with cols[1]:
        st.metric(gui_t("match_center.live", locale), len(snapshot.live))
    with cols[2]:
        st.metric(gui_t("match_center.finished", locale), len(snapshot.finished))

    tab_up, tab_live, tab_fin = st.tabs(
        [
            gui_t("match_center.upcoming", locale),
            gui_t("match_center.live", locale),
            gui_t("match_center.finished", locale),
        ]
    )

    with tab_up:
        _render_fixture_list(snapshot.upcoming[:30], locale, key_prefix="eu_up")
    with tab_live:
        _render_fixture_list(snapshot.live[:30], locale, key_prefix="eu_live")
    with tab_fin:
        _render_fixture_list(snapshot.finished[:30], locale, key_prefix="eu_fin")

    fid = st.session_state.get("european_selected_fixture")
    if fid:
        st.markdown("---")
        st.subheader(gui_t("european.predict_match", locale))
        render_match_action_panel(
            int(fid),
            settings=settings,
            locale=locale,
            competition_key=competition_key,
        )


def _render_fixture_list(
    fixtures: list[Any],
    locale: Locale,
    *,
    key_prefix: str,
) -> None:
    if not fixtures:
        st.caption(gui_t("european.empty_section", locale))
        return
    for fx in fixtures:
        kickoff = fx.kickoff_time.strftime("%Y-%m-%d %H:%M") if fx.kickoff_time else "TBD"
        label = f"{fx.home_team} vs {fx.away_team} · {kickoff} · {fx.status}"
        if st.button(label, key=f"{key_prefix}_{fx.fixture_id}", use_container_width=True):
            st.session_state["european_selected_fixture"] = fx.fixture_id
            st.rerun()
