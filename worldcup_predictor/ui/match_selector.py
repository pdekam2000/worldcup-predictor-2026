"""Searchable match selector — team names instead of fixture IDs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.ui.gui_i18n import gui_t


def format_match_label(fixture: TournamentFixture) -> str:
    kickoff = fixture.kickoff_time
    if kickoff:
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        date_part = kickoff.strftime("%d %b %Y %H:%M")
    else:
        date_part = "TBD"
    return f"{fixture.home_team} vs {fixture.away_team} — {date_part}"


def filter_fixtures(fixtures: list[TournamentFixture], query: str) -> list[TournamentFixture]:
    needle = query.strip().lower()
    if not needle:
        return fixtures
    matched: list[TournamentFixture] = []
    for fixture in fixtures:
        haystack = f"{fixture.home_team} {fixture.away_team} {format_match_label(fixture)}".lower()
        if needle in haystack:
            matched.append(fixture)
    return matched


def sort_fixtures(fixtures: list[TournamentFixture]) -> list[TournamentFixture]:
    def _key(item: TournamentFixture) -> datetime:
        if item.kickoff_time:
            kt = item.kickoff_time
            if kt.tzinfo is None:
                return kt.replace(tzinfo=timezone.utc)
            return kt
        return datetime.max.replace(tzinfo=timezone.utc)

    return sorted(fixtures, key=_key)


def render_match_selector(
    fixtures: list[TournamentFixture],
    locale: Locale,
    *,
    key_prefix: str,
    default_fixture_id: int | None = None,
    show_advanced_id: bool = False,
    on_select: Any | None = None,
) -> int | None:
    """Searchable dropdown; returns selected fixture_id."""
    ordered = sort_fixtures(fixtures)
    if not ordered:
        st.warning(gui_t("no_fixture", locale))
        return default_fixture_id

    search_key = f"{key_prefix}_match_search"
    select_key = f"{key_prefix}_match_select"
    query = st.text_input(
        gui_t("match_selector.search", locale),
        placeholder=gui_t("match_selector.placeholder", locale),
        key=search_key,
    )
    filtered = filter_fixtures(ordered, query)
    if not filtered:
        st.info(gui_t("match_selector.no_results", locale))
        filtered = ordered

    labels = {format_match_label(f): f.fixture_id for f in filtered}
    label_list = list(labels.keys())
    default_label = label_list[0]
    if default_fixture_id is not None:
        for label, fid in labels.items():
            if fid == default_fixture_id:
                default_label = label
                break

    selected_label = st.selectbox(
        gui_t("match_selector.label", locale),
        label_list,
        index=label_list.index(default_label),
        key=select_key,
    )
    fixture_id = labels[selected_label]
    selected = next(f for f in filtered if f.fixture_id == fixture_id)
    st.session_state["selected_fixture_id"] = fixture_id
    st.session_state["fixture_id"] = fixture_id
    st.session_state["selected_match_name"] = f"{selected.home_team} vs {selected.away_team}"

    if show_advanced_id:
        with st.expander(gui_t("match_selector.advanced", locale), expanded=False):
            st.caption(f"Fixture ID: **{fixture_id}**")

    if on_select is not None:
        on_select(selected)
    return fixture_id
