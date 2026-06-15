"""Shared fixture list navigation: anchors, filters, date sections, back-to-top."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.fixture_list_helpers import FilterKey, filter_fixtures, group_fixtures_by_date
from worldcup_predictor.ui.gui_i18n import gui_t


def render_page_top_anchor() -> None:
    st.markdown('<div id="page-top"></div>', unsafe_allow_html=True)


def render_back_to_top(locale: Locale) -> None:
    label = gui_t("nav.back_to_top", locale)
    st.markdown(
        f'<a href="#page-top" class="back-to-top" title="{label}">{label}</a>',
        unsafe_allow_html=True,
    )


def render_fixture_quick_filters(locale: Locale, *, key_prefix: str) -> FilterKey:
    options: list[tuple[FilterKey, str]] = [
        ("today", f"📅 {gui_t('filter.today', locale)}"),
        ("tomorrow", f"🌅 {gui_t('filter.tomorrow', locale)}"),
        ("next_3_days", f"📆 {gui_t('filter.next_3_days', locale)}"),
        ("favorites", f"⭐ {gui_t('filter.favorites', locale)}"),
        ("all", f"🌍 {gui_t('filter.all', locale)}"),
    ]
    labels = [label for _, label in options]
    keys = [key for key, _ in options]
    default_idx = keys.index("all")
    st.markdown('<div class="sticky-match-toolbar"><div class="filter-pills">', unsafe_allow_html=True)
    choice = st.radio(
        gui_t("filter.label", locale),
        labels,
        index=default_idx,
        horizontal=True,
        key=f"{key_prefix}_fixture_filter",
        label_visibility="collapsed",
    )
    st.markdown("</div></div>", unsafe_allow_html=True)
    return keys[labels.index(choice)]


def render_grouped_fixture_list(
    fixtures: list[Any],
    locale: Locale,
    render_row: Callable[[Any], None],
    *,
    filter_key: FilterKey | None = None,
    favorite_ids: set[int] | None = None,
    empty_message: str = "No matches found.",
) -> None:
    favs = favorite_ids or set(st.session_state.get("favorite_fixtures") or set())
    filtered = (
        filter_fixtures(fixtures, filter_key, favorite_ids=favs)
        if filter_key
        else list(fixtures)
    )
    if not filtered:
        st.info(empty_message)
        return

    groups = group_fixtures_by_date(
        filtered,
        locale_label_today=gui_t("filter.today", locale),
        locale_label_tomorrow=gui_t("filter.tomorrow", locale),
    )
    for section_label, section_fixtures in groups:
        st.markdown(f"### {section_label}")
        for fixture in section_fixtures:
            render_row(fixture)
