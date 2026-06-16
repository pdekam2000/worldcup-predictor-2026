"""World Cup Group Browser — Match Prediction discovery UX."""

from __future__ import annotations

import re
from typing import Any, Callable

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, LIVE_STATUSES
from worldcup_predictor.ui.fixture_display import format_kickoff_caption
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.professional_reports_page import list_exported_reports
from worldcup_predictor.ui.stored_prediction_summary import has_stored_prediction


GROUP_KEYS = tuple(f"Group {letter}" for letter in "ABCDEFGH")


def _fixture_id(fixture: Any) -> int:
    return int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0) or 0)


def _resolve_group(fixture: Any) -> str | None:
    raw = getattr(fixture, "group", None) or ""
    if raw and str(raw).startswith("Group"):
        return str(raw).strip()
    stage = getattr(fixture, "round", None) or getattr(fixture, "stage", None) or ""
    match = re.search(r"Group\s+([A-H])\b", str(stage), re.IGNORECASE)
    if match:
        return f"Group {match.group(1).upper()}"
    return None


def _group_fixtures(all_fixtures: list[Any]) -> dict[str, list[Any]]:
    buckets: dict[str, list[Any]] = {g: [] for g in GROUP_KEYS}
    for fixture in all_fixtures:
        group = _resolve_group(fixture)
        if group and group in buckets:
            buckets[group].append(fixture)
    for group in buckets:
        buckets[group].sort(key=lambda f: getattr(f, "kickoff_time", None) or getattr(f, "kickoff_utc", None))
    return buckets


def _is_finished(fixture: Any) -> bool:
    return (getattr(fixture, "status", "") or "").upper() in FINISHED_STATUSES


def _is_live(fixture: Any) -> bool:
    return (getattr(fixture, "status", "") or "").upper() in LIVE_STATUSES


def _score_line(fixture: Any) -> str:
    hg = getattr(fixture, "home_goals", None)
    ag = getattr(fixture, "away_goals", None)
    if hg is not None and ag is not None:
        return f"{hg}-{ag}"
    return "—"


def _has_export_report(fixture_id: int) -> bool:
    try:
        return any(item.fixture_id == fixture_id for item in list_exported_reports(limit=200))
    except Exception:
        return False


def _match_row_class(fixture: Any) -> str:
    if _is_live(fixture):
        return "match-row-live"
    if _is_finished(fixture):
        return "match-row-finished"
    return "match-row-upcoming"


def _badge_html(fixture: Any, locale: Locale) -> str:
    if _is_live(fixture):
        score = _score_line(fixture)
        label = gui_t("status.live", locale)
        if score != "—":
            label = f"{label} · {score}"
        return f'<span class="match-badge match-badge-live">{label}</span>'
    if _is_finished(fixture):
        home = getattr(fixture, "home_team", "—")
        away = getattr(fixture, "away_team", "—")
        score = _score_line(fixture)
        result = f"{home} {score} {away}" if score != "—" else _score_line(fixture)
        return (
            f'<span class="match-badge match-badge-finished">{gui_t("status.finished", locale)}</span> '
            f'<span class="match-result-text">{result}</span>'
        )
    return f'<span class="match-badge match-badge-upcoming">{gui_t("status.upcoming", locale)}</span>'


def render_worldcup_group_browser(
    locale: Locale,
    *,
    all_fixtures: list[Any],
    groups: dict[str, Any] | None,
    on_select_fixture: Callable[[int], None],
    key_prefix: str = "wc_group",
) -> None:
    """Group A–H browser with played/upcoming matches — never raises."""
    try:
        _render(locale, all_fixtures, groups, on_select_fixture, key_prefix)
    except Exception:
        st.caption(gui_t("group_browser.unavailable", locale))


def _standing_rows(wc_group: Any) -> list[Any]:
    if wc_group is None:
        return []
    standings = getattr(wc_group, "standings", None)
    if standings is None and isinstance(wc_group, dict):
        standings = wc_group.get("standings") or []
    return list(standings or [])


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _render_group_standings(wc_group: Any, locale: Locale) -> None:
    rows = _standing_rows(wc_group)
    if not rows:
        return
    st.markdown(f"**{gui_t('group_browser.standings', locale)}**")
    table_rows: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: _row_value(r, "rank", 99) or 99):
        table_rows.append(
            {
                "#": _row_value(row, "rank", "—"),
                gui_t("group_browser.team", locale): _row_value(row, "team_name", "—"),
                "P": _row_value(row, "played", 0),
                "W": _row_value(row, "won", 0),
                "D": _row_value(row, "drawn", 0),
                "L": _row_value(row, "lost", 0),
                "GD": _row_value(row, "goal_difference", 0),
                gui_t("standings.points", locale): _row_value(row, "points", 0),
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def _render(
    locale: Locale,
    all_fixtures: list[Any],
    groups: dict[str, Any] | None,
    on_select_fixture: Callable[[int], None],
    key_prefix: str,
) -> None:
    st.markdown(f"### {gui_t('group_browser.title', locale)}")
    st.caption(gui_t("group_browser.subtitle", locale))

    by_group = _group_fixtures(all_fixtures)
    cols = st.columns(4)
    for idx, group_name in enumerate(GROUP_KEYS):
        with cols[idx % 4]:
            teams: list[str] = []
            wc_group = (groups or {}).get(group_name)
            if wc_group and getattr(wc_group, "standings", None):
                teams = [row.team_name for row in wc_group.standings[:4]]
            elif wc_group and isinstance(wc_group, dict):
                teams = [r.get("team_name", "") for r in wc_group.get("standings", [])[:4]]
            fixtures = by_group.get(group_name, [])
            played = sum(1 for f in fixtures if _is_finished(f))
            live = sum(1 for f in fixtures if _is_live(f))
            upcoming = sum(1 for f in fixtures if not _is_finished(f) and not _is_live(f))
            label = group_name.replace("Group ", "")
            with st.container(border=True):
                st.markdown(f'<div class="group-card-glass"><div class="group-card-header">{group_name}</div>', unsafe_allow_html=True)
                if teams:
                    st.markdown(
                        '<div class="group-card-teams">' + " · ".join(teams) + "</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption(gui_t("group_browser.teams_pending", locale))
                st.caption(
                    f"{gui_t('group_browser.played', locale)}: {played} · "
                    f"{gui_t('status.live', locale)}: {live} · "
                    f"{gui_t('group_browser.upcoming', locale)}: {upcoming}"
                )
                expand = st.session_state.get("gui_expand_group_browser") and idx == 0
                with st.expander(gui_t("group_browser.open", locale).format(group=label), expanded=expand):
                    if wc_group:
                        _render_group_standings(wc_group, locale)
                    if not fixtures:
                        st.caption(gui_t("group_browser.no_fixtures", locale))
                        continue
                    live_rows = [f for f in fixtures if _is_live(f)]
                    finished_rows = [f for f in fixtures if _is_finished(f)]
                    open_rows = [f for f in fixtures if not _is_finished(f) and not _is_live(f)]
                    if live_rows:
                        st.markdown(f"**{gui_t('status.live', locale)}**")
                        for fixture in live_rows:
                            _render_fixture_row(fixture, locale, on_select_fixture, key_prefix, show_predict=True)
                    if finished_rows:
                        st.markdown(f"**{gui_t('group_browser.results', locale)}**")
                        for fixture in finished_rows:
                            _render_fixture_row(fixture, locale, on_select_fixture, key_prefix, show_predict=False)
                    if open_rows:
                        st.markdown(f"**{gui_t('group_browser.fixtures', locale)}**")
                        for fixture in open_rows:
                            _render_fixture_row(fixture, locale, on_select_fixture, key_prefix, show_predict=True)


def _render_fixture_row(
    fixture: Any,
    locale: Locale,
    on_select_fixture: Callable[[int], None],
    key_prefix: str,
    *,
    show_predict: bool,
) -> None:
    fid = _fixture_id(fixture)
    home = getattr(fixture, "home_team", "—")
    away = getattr(fixture, "away_team", "—")
    local_ko, utc_ko = format_kickoff_times(
        getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None),
        venue_city=getattr(fixture, "city", None),
        venue_country=getattr(fixture, "country", None),
    )
    ko_caption = format_kickoff_caption(fixture, locale)
    status = getattr(fixture, "status", "NS")
    row_class = _match_row_class(fixture)

    st.markdown(
        f'<div class="match-row {row_class}">{_badge_html(fixture, locale)}</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"**{home} vs {away}**")
        if _is_finished(fixture):
            st.caption(f"{ko_caption} · ID {fid}")
            st.caption(f'<span class="match-status-struck">~~{status}~~</span>', unsafe_allow_html=True)
        else:
            st.caption(ko_caption)
            st.caption(f"ID {fid}", help=gui_t("card.fixture_id", locale))
    with c2:
        if show_predict and st.button(gui_t("btn.predict_match", locale), key=f"{key_prefix}_pred_{fid}", use_container_width=True):
            on_select_fixture(fid)
        if _has_export_report(fid):
            if st.button(gui_t("group_browser.view_report", locale), key=f"{key_prefix}_rep_{fid}", use_container_width=True):
                st.session_state["gui_page"] = "professional_reports"
                st.session_state["reports_filter_fixture_id"] = fid
                st.rerun()
        elif has_stored_prediction(fid) and st.button(
            gui_t("group_browser.view_prediction", locale),
            key=f"{key_prefix}_view_{fid}",
            use_container_width=True,
        ):
            on_select_fixture(fid)
    st.markdown('<hr class="match-row-divider"/>', unsafe_allow_html=True)
