"""Phase 39A — Competition mode selector for GUI sidebar."""

from __future__ import annotations

import streamlit as st

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY
from worldcup_predictor.config.league_registry import (
    COMPETITION_MODE_EUROPEAN,
    COMPETITION_MODE_WORLD_CUP,
    default_competition_for_mode,
    season_options_for,
)
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def render_competition_mode_selector(locale: Locale) -> None:
    """World Cup vs European Leagues mode with league + season dropdowns."""
    modes = [COMPETITION_MODE_WORLD_CUP, COMPETITION_MODE_EUROPEAN]
    mode_labels = {
        COMPETITION_MODE_WORLD_CUP: gui_t("competition.mode_world_cup", locale),
        COMPETITION_MODE_EUROPEAN: gui_t("competition.mode_european", locale),
    }
    current_mode = st.session_state.get("competition_mode", COMPETITION_MODE_WORLD_CUP)
    if current_mode not in modes:
        current_mode = COMPETITION_MODE_WORLD_CUP

    selected_mode = st.sidebar.selectbox(
        gui_t("competition.mode", locale),
        modes,
        index=modes.index(current_mode),
        format_func=lambda m: mode_labels[m],
        key="competition_mode_select",
    )
    st.session_state["competition_mode"] = selected_mode

    if selected_mode == COMPETITION_MODE_WORLD_CUP:
        st.session_state["competition"] = DEFAULT_COMPETITION_KEY
        comp = CompetitionService().get_competition(DEFAULT_COMPETITION_KEY)
        seasons = season_options_for(comp.key)
        default_season = comp.season
        st.session_state["competition_season"] = default_season
        st.sidebar.caption(f"{comp.display_name} · {default_season}")
        return

    european = CompetitionService().list_european_leagues()
    if not european:
        st.sidebar.warning(gui_t("competition.no_leagues", locale))
        return

    league_keys = [c.key for c in european]
    league_labels = {c.key: f"🏟️ {c.display_name}" for c in european}
    current_key = st.session_state.get("competition", league_keys[0])
    if current_key not in league_keys:
        current_key = default_competition_for_mode(COMPETITION_MODE_EUROPEAN)

    st.session_state["competition"] = st.sidebar.selectbox(
        gui_t("competition.league", locale),
        league_keys,
        index=league_keys.index(current_key),
        format_func=lambda k: league_labels[k],
        key="european_league_select",
    )

    comp_key = st.session_state["competition"]
    seasons = season_options_for(comp_key)
    current_season = st.session_state.get("competition_season")
    if current_season not in seasons:
        current_season = seasons[-1] if seasons else CompetitionService().get_default_season(comp_key)

    st.session_state["competition_season"] = st.sidebar.selectbox(
        gui_t("competition.season", locale),
        seasons,
        index=seasons.index(current_season) if current_season in seasons else len(seasons) - 1,
        key="competition_season_select",
    )


def competition_season() -> int | None:
    return st.session_state.get("competition_season")
