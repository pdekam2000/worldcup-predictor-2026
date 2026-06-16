"""Premium User Mode home dashboard — dark sports analytics style."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, LIVE_STATUSES
from worldcup_predictor.ui.app_shell import render_dashboard_footer
from worldcup_predictor.ui.fixture_display import format_group_stage, format_kickoff_times
from worldcup_predictor.ui.fixture_list_helpers import is_kickoff_today
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.gui_mode_v2 import navigate_to_page
from worldcup_predictor.ui.worldcup_group_browser import render_worldcup_group_browser


def _fixture_id(fixture: Any) -> int:
    return int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0) or 0)


def _status_key(fixture: Any) -> str:
    code = (getattr(fixture, "status", None) or "NS").upper()
    if code in LIVE_STATUSES:
        return "live"
    if code in FINISHED_STATUSES:
        return "finished"
    return "upcoming"


def _next_matches(center: Any, *, limit: int = 4) -> list[Any]:
    pools = list(getattr(center, "live", []) or []) + list(getattr(center, "upcoming", []) or [])
    seen: set[int] = set()
    out: list[Any] = []
    for fixture in pools:
        fid = _fixture_id(fixture)
        if fid in seen:
            continue
        seen.add(fid)
        out.append(fixture)
    out.sort(key=lambda f: getattr(f, "kickoff_time", None) or getattr(f, "kickoff_utc", None))
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


def _render_welcome_header(locale: Locale) -> None:
    st.markdown(
        f"""
<div class="dash-welcome-header">
  <h1>{gui_t("home.dashboard_title", locale)}</h1>
  <p>{gui_t("home.dashboard_subtitle", locale)}</p>
</div>
""",
        unsafe_allow_html=True,
    )


def _render_match_card_html(fixture: Any, locale: Locale) -> str:
    home = getattr(fixture, "home_team", "—")
    away = getattr(fixture, "away_team", "—")
    kickoff = getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None)
    local_ko, _ = format_kickoff_times(kickoff)
    group = format_group_stage(fixture)
    status = _status_key(fixture)
    badge = gui_t("status.live", locale) if status == "live" else gui_t("status.upcoming", locale)
    badge_class = "dash-badge-live" if status == "live" else "dash-badge-user"
    return f"""
<div class="dash-match-card">
  <div class="dash-match-teams">{home} vs {away}</div>
  <div class="dash-match-meta">
    <span class="dash-match-group">{group}</span><br/>
    {local_ko}<br/>
    <span class="dash-badge {badge_class}">{badge}</span>
  </div>
</div>
"""


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
    _render_welcome_header(locale)

    top_left, top_right = st.columns([3, 1])
    with top_right:
        st.markdown(
            f'<span class="dash-badge dash-badge-user">{gui_t("mode.user", locale)}</span>',
            unsafe_allow_html=True,
        )

    st.markdown(f'<div class="dash-section-title">📅 {gui_t("home.next_matches", locale)}</div>', unsafe_allow_html=True)
    next_rows = _next_matches(center, limit=4)
    if next_rows:
        cols = st.columns(min(len(next_rows), 4))
        for col, fixture in zip(cols, next_rows):
            with col:
                st.markdown(_render_match_card_html(fixture, locale), unsafe_allow_html=True)
                fid = _fixture_id(fixture)
                if _status_key(fixture) != "finished" and fid:
                    if st.button(gui_t("btn.predict_match", locale), key=f"home_nm_{fid}", use_container_width=True):
                        _select_fixture(fid)
    else:
        st.info(gui_t("no_fixture", locale))

    st.markdown(f'<div class="dash-section-title">⚡ {gui_t("home.quick_actions", locale)}</div>', unsafe_allow_html=True)
    actions = [
        ("match_center", "btn.match_center", "🏟️", goto_match_center),
        ("team_search", "nav.game_search", "🔎", None),
        ("finished_results", "nav.finished_results", "✅", None),
        ("professional_reports", "nav.professional_reports", "📄", goto_reports),
        ("hall_of_fame", "nav.hall_of_fame", "🏆", None),
        ("settings", "nav.settings", "⚙️", None),
    ]
    qcols = st.columns(3)
    for idx, (page, i18n, icon, callback) in enumerate(actions):
        with qcols[idx % 3]:
            if st.button(f"{icon} {gui_t(i18n, locale)}", key=f"home_qa_{page}", use_container_width=True):
                if callback:
                    callback()
                else:
                    _nav(page)

    if all_fixtures:
        st.markdown(f'<div class="dash-section-title">🌍 {gui_t("group_browser.title", locale)}</div>', unsafe_allow_html=True)
        render_worldcup_group_browser(
            locale,
            all_fixtures=all_fixtures,
            groups=groups,
            on_select_fixture=_select_fixture,
            key_prefix="home_groups",
        )

    st.markdown(f'<div class="dash-section-title">🤖 {gui_t("home.ai_insights", locale)}</div>', unsafe_allow_html=True)
    if last_prediction and getattr(last_prediction, "success", False):
        pred = last_prediction.prediction
        score = f"{int(pred.scoreline.home_goals)}-{int(pred.scoreline.away_goals)}"
        ou_prob = f"{pred.over_under.probability * 100:.0f}%" if pred.over_under.probability else "—"
        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1:
            st.markdown(
                f'<div class="dash-insight-card"><div class="dash-insight-label">{gui_t("home.top_prediction", locale)}</div>'
                f'<div class="dash-insight-value">{_format_1x2(pred.one_x_two.selection, pred.match_name.split(" vs ")[0] if " vs " in pred.match_name else "", "")}</div></div>',
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
                f'<div class="dash-insight-label">{ou_prob}</div></div>',
                unsafe_allow_html=True,
            )
        with ic4:
            st.markdown(
                f'<div class="dash-insight-card"><div class="dash-insight-label">{gui_t("badge.confidence", locale)}</div>'
                f'<div class="dash-insight-value">{pred.confidence_score:.0f}</div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption(gui_t("home.no_prediction_yet", locale))

    st.markdown(f'<div class="dash-section-title">📊 {gui_t("home.recent_predictions", locale)}</div>', unsafe_allow_html=True)
    if last_prediction and getattr(last_prediction, "success", False):
        pred = last_prediction.prediction
        score = f"{int(pred.scoreline.home_goals)}-{int(pred.scoreline.away_goals)}"
        st.markdown(
            f"""
<div class="glass-card">
  <strong>{pred.match_name}</strong><br/>
  <span class="dash-badge dash-badge-user">{_format_1x2(pred.one_x_two.selection, "", "")}</span>
  <span class="dash-badge dash-badge-user">{_format_ou(pred.over_under.selection)}</span>
  <span class="dash-badge dash-badge-user">{score}</span><br/>
  <span style="color:#94a3b8;font-size:0.8rem;">{gui_t("badge.confidence", locale)}: {pred.confidence_score:.0f}/100</span>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.caption(gui_t("home.no_prediction_yet", locale))

    render_dashboard_footer(locale, live_status=gui_t("footer.live", locale) if api_ready else "Demo")
