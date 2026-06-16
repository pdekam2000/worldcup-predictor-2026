"""Premium User Mode home dashboard — modern flag-forward layout."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, LIVE_STATUSES
from worldcup_predictor.ui.app_shell import render_dashboard_footer
from worldcup_predictor.ui.fixture_display import format_group_stage, format_kickoff_hero
from worldcup_predictor.ui.fixture_list_helpers import is_kickoff_today, local_kickoff_time_display
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.team_display import match_showcase_html
from worldcup_predictor.ui.gui_mode_v2 import navigate_to_page
from worldcup_predictor.ui.worldcup_group_browser import render_worldcup_group_browser


def _fixture_id(fixture: Any) -> int:
    return int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0) or 0)


def _kickoff_sort_key(fixture: Any) -> Any:
    return getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None)


def _status_key(fixture: Any) -> str:
    code = (getattr(fixture, "status", None) or "NS").upper()
    if code in LIVE_STATUSES:
        return "live"
    if code in FINISHED_STATUSES:
        return "finished"
    return "upcoming"


def _today_fixtures(center: Any) -> list[Any]:
    pools = (
        list(getattr(center, "live", []) or [])
        + list(getattr(center, "upcoming", []) or [])
        + list(getattr(center, "finished", []) or [])
    )
    seen: set[int] = set()
    out: list[Any] = []
    for fixture in pools:
        if not is_kickoff_today(fixture):
            continue
        fid = _fixture_id(fixture)
        if fid in seen:
            continue
        seen.add(fid)
        out.append(fixture)
    out.sort(key=_kickoff_sort_key)
    return out


def _next_matches(center: Any, *, limit: int = 4, exclude_ids: set[int] | None = None) -> list[Any]:
    skip = exclude_ids or set()
    pools = list(getattr(center, "live", []) or []) + list(getattr(center, "upcoming", []) or [])
    seen: set[int] = set()
    out: list[Any] = []
    for fixture in pools:
        fid = _fixture_id(fixture)
        if fid in seen or fid in skip:
            continue
        seen.add(fid)
        out.append(fixture)
    out.sort(key=_kickoff_sort_key)
    return out[:limit]


def _select_fixture(fixture_id: int) -> None:
    st.session_state["selected_fixture_id"] = fixture_id
    st.session_state["fixture_id"] = fixture_id
    st.session_state["gui_page"] = "predict"
    st.rerun()


def _nav(page: str) -> None:
    navigate_to_page(page, developer_mode=False)
    st.rerun()


def _format_ou(selection: str) -> str:
    key = (selection or "").lower()
    if "over" in key:
        return "Over 2.5"
    if "under" in key:
        return "Under 2.5"
    return selection.replace("_", " ").title()


def _format_1x2(selection: str, home: str, away: str) -> str:
    key = (selection or "").lower().replace(" ", "_")
    if key == "home_win":
        return f"{home} Win"
    if key == "away_win":
        return f"{away} Win"
    if key == "draw":
        return "Draw"
    return selection.replace("_", " ").title()


def _showcase_card_html(fixture: Any, locale: Locale) -> str:
    home = getattr(fixture, "home_team", "—")
    away = getattr(fixture, "away_team", "—")
    status = _status_key(fixture)
    group = format_group_stage(fixture)
    time_line, date_line, venue_line = format_kickoff_hero(fixture, locale)
    if status == "live":
        badge = gui_t("home.live_now", locale)
        badge_class = "dash-badge-live"
        time_line = local_kickoff_time_display(fixture) or time_line
    elif status == "finished":
        badge = gui_t("status.finished", locale)
        badge_class = "dash-badge-finished"
        score_h = getattr(fixture, "home_score", None)
        score_a = getattr(fixture, "away_score", None)
        if score_h is not None and score_a is not None:
            time_line = f"{score_h} – {score_a}"
    else:
        badge = gui_t("status.upcoming", locale)
        badge_class = "dash-badge-user"

    showcase = match_showcase_html(
        home,
        away,
        fixture=fixture,
        country_hint=getattr(fixture, "country", None),
    )
    venue_html = f'<div class="showcase-venue">{venue_line}</div>' if venue_line else ""
    return f"""
<div class="showcase-card">
  <div class="showcase-card-top">
    <span class="dash-badge {badge_class}">{badge}</span>
    <span class="showcase-group">{group}</span>
  </div>
  {showcase}
  <div class="showcase-kickoff">
    <span class="showcase-time">{time_line}</span>
    <span class="showcase-date">{date_line}</span>
  </div>
  {venue_html}
</div>
"""


def render_home_match_showcase(
    fixtures: list[Any],
    locale: Locale,
    *,
    key_prefix: str = "home",
    on_select: Callable[[int], None] | None = None,
    show_predict: bool = True,
) -> None:
    """Large flag-forward match cards — shared by user and developer home."""
    if not fixtures:
        return
    select = on_select or _select_fixture
    count = len(fixtures)
    cols = st.columns(min(count, 3))
    for col, fixture in zip(cols, fixtures[:3]):
        with col:
            st.markdown(_showcase_card_html(fixture, locale), unsafe_allow_html=True)
            fid = _fixture_id(fixture)
            if show_predict and _status_key(fixture) != "finished" and fid:
                if st.button(
                    gui_t("btn.predict_match", locale),
                    key=f"{key_prefix}_sc_{fid}",
                    use_container_width=True,
                    type="primary",
                ):
                    select(fid)
    if count > 3:
        extra = fixtures[3:6]
        cols2 = st.columns(min(len(extra), 3))
        for col, fixture in zip(cols2, extra):
            with col:
                st.markdown(_showcase_card_html(fixture, locale), unsafe_allow_html=True)
                fid = _fixture_id(fixture)
                if show_predict and _status_key(fixture) != "finished" and fid:
                    if st.button(
                        gui_t("btn.predict_match", locale),
                        key=f"{key_prefix}_sc2_{fid}",
                        use_container_width=True,
                    ):
                        select(fid)


def render_user_home_dashboard(
    locale: Locale,
    *,
    center: Any,
    api_ready: bool,
    last_prediction: Any | None,
    all_fixtures: list[Any] | None = None,
    groups: dict[str, Any] | None = None,
    on_quick_predict: Callable[[], None] | None = None,
    goto_predict: Callable[[], None] | None = None,
    goto_reports: Callable[[], None] | None = None,
    goto_match_center: Callable[[], None] | None = None,
) -> None:
    """Premium home dashboard — never raises."""
    try:
        _render(
            locale,
            center,
            api_ready,
            last_prediction,
            all_fixtures or [],
            groups,
            goto_predict,
            goto_reports,
            goto_match_center,
        )
    except Exception:
        st.info(gui_t("home.user_welcome", locale))


def _render_hero(locale: Locale, *, match_count: int, live_count: int) -> None:
    live_pill = ""
    if live_count:
        live_pill = f'<span class="dash-badge dash-badge-live">{live_count} {gui_t("home.live_now", locale)}</span>'
    st.markdown(
        f"""
<div class="dash-hero">
  <div class="dash-hero-glow"></div>
  <div class="dash-hero-content">
    <div class="dash-hero-kicker">World Cup 2026</div>
    <h1>{gui_t("home.dashboard_title", locale)}</h1>
    <p>{gui_t("home.dashboard_subtitle", locale)}</p>
    <div class="dash-hero-stats">
      {live_pill}
      <span class="dash-hero-stat">{match_count} {gui_t("home.today_matches", locale)}</span>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _render(
    locale: Locale,
    center: Any,
    api_ready: bool,
    last_prediction: Any | None,
    all_fixtures: list[Any],
    groups: dict[str, Any] | None,
    goto_predict: Callable[[], None] | None,
    goto_reports: Callable[[], None] | None,
    goto_match_center: Callable[[], None] | None,
) -> None:
    today_rows = _today_fixtures(center)
    live_count = sum(1 for f in today_rows if _status_key(f) == "live")
    _render_hero(locale, match_count=len(today_rows), live_count=live_count)

    st.markdown(
        f'<div class="dash-section-title dash-section-featured">🏟️ {gui_t("home.today_matches", locale)}</div>',
        unsafe_allow_html=True,
    )
    if today_rows:
        render_home_match_showcase(today_rows, locale, key_prefix="home_today")
    else:
        st.info(gui_t("home.no_match_today_next", locale))
        fallback = _next_matches(center, limit=3)
        if fallback:
            render_home_match_showcase(fallback, locale, key_prefix="home_next")

    today_ids = {_fixture_id(f) for f in today_rows}
    upcoming_extra = _next_matches(center, limit=4, exclude_ids=today_ids)
    if upcoming_extra:
        st.markdown(
            f'<div class="dash-section-title">📅 {gui_t("home.next_matches", locale)}</div>',
            unsafe_allow_html=True,
        )
        row_cols = st.columns(min(len(upcoming_extra), 4))
        for col, fixture in zip(row_cols, upcoming_extra):
            with col:
                st.markdown(_showcase_card_html(fixture, locale), unsafe_allow_html=True)
                fid = _fixture_id(fixture)
                if _status_key(fixture) != "finished" and fid:
                    if st.button(gui_t("btn.predict_match", locale), key=f"home_nm_{fid}", use_container_width=True):
                        _select_fixture(fid)

    st.markdown(
        f'<div class="dash-section-title">⚡ {gui_t("home.quick_actions", locale)}</div>',
        unsafe_allow_html=True,
    )
    actions = [
        ("match_center", "btn.match_center", "🏟️", goto_match_center),
        ("team_search", "nav.game_search", "🔎", None),
        ("predict", "nav.predict", "🎯", goto_predict),
        ("finished_results", "nav.finished_results", "✅", None),
        ("professional_reports", "nav.professional_reports", "📄", goto_reports),
        ("hall_of_fame", "nav.hall_of_fame", "🏆", None),
    ]
    qcols = st.columns(3)
    for idx, (page, i18n, icon, callback) in enumerate(actions):
        with qcols[idx % 3]:
            if st.button(f"{icon} {gui_t(i18n, locale)}", key=f"home_qa_{page}", use_container_width=True):
                if callback:
                    callback()
                else:
                    _nav(page)

    if last_prediction and getattr(last_prediction, "success", False):
        st.markdown(
            f'<div class="dash-section-title">🤖 {gui_t("home.ai_insights", locale)}</div>',
            unsafe_allow_html=True,
        )
        pred = last_prediction.prediction
        parts = pred.match_name.split(" vs ", 1) if " vs " in pred.match_name else [pred.match_name, ""]
        home_name, away_name = parts[0], parts[1] if len(parts) > 1 else ""
        score = f"{int(pred.scoreline.home_goals)}-{int(pred.scoreline.away_goals)}"
        ou_prob = f"{pred.over_under.probability * 100:.0f}%" if pred.over_under.probability else "—"
        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1:
            st.markdown(
                f'<div class="dash-insight-card"><div class="dash-insight-label">{gui_t("home.top_prediction", locale)}</div>'
                f'<div class="dash-insight-value">{_format_1x2(pred.one_x_two.selection, home_name, away_name)}</div></div>',
                unsafe_allow_html=True,
            )
        with ic2:
            st.markdown(
                f'<div class="dash-insight-card"><div class="dash-insight-label">{gui_t("home.likely_score", locale)}</div>'
                f'<div class="dash-insight-value">{score}</div></div>',
                unsafe_allow_html=True,
            )
        with ic3:
            st.markdown(
                f'<div class="dash-insight-card"><div class="dash-insight-label">O/U 2.5</div>'
                f'<div class="dash-insight-value">{_format_ou(pred.over_under.selection)}</div>'
                f'<div class="dash-insight-sub">{ou_prob}</div></div>',
                unsafe_allow_html=True,
            )
        with ic4:
            st.markdown(
                f'<div class="dash-insight-card"><div class="dash-insight-label">{gui_t("badge.confidence", locale)}</div>'
                f'<div class="dash-insight-value">{pred.confidence_score:.0f}</div></div>',
                unsafe_allow_html=True,
            )

    if all_fixtures:
        with st.expander(f"🌍 {gui_t('group_browser.title', locale)}", expanded=False):
            render_worldcup_group_browser(
                locale,
                all_fixtures=all_fixtures,
                groups=groups,
                on_select_fixture=_select_fixture,
                key_prefix="home_groups",
            )

    render_dashboard_footer(locale, live_status=gui_t("footer.live", locale) if api_ready else "Demo")
