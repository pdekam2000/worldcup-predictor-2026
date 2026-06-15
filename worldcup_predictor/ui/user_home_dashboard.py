"""Today-focused User Mode home dashboard — Phase Product UX."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES, LIVE_STATUSES
from worldcup_predictor.ui.fixture_display import format_group_stage, format_kickoff_times
from worldcup_predictor.ui.fixture_list_helpers import is_kickoff_today
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.status_badges import render_status_badge


def _fixture_id(fixture: Any) -> int:
    return int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0) or 0)


def _status_key(fixture: Any) -> str:
    code = (getattr(fixture, "status", None) or "NS").upper()
    if code in LIVE_STATUSES:
        return "live"
    if code in FINISHED_STATUSES:
        return "finished"
    return "upcoming"


def _today_fixtures(center: Any) -> list[Any]:
    pools = list(getattr(center, "live", []) or []) + list(getattr(center, "upcoming", []) or [])
    pools += list(getattr(center, "finished", []) or [])
    seen: set[int] = set()
    today_list: list[Any] = []
    for fixture in pools:
        fid = _fixture_id(fixture)
        if fid in seen or not is_kickoff_today(fixture):
            continue
        seen.add(fid)
        today_list.append(fixture)
    today_list.sort(key=lambda f: getattr(f, "kickoff_time", None) or getattr(f, "kickoff_utc", None))
    return today_list


def _next_upcoming(center: Any, *, exclude_today: bool) -> Any | None:
    upcoming = sorted(
        getattr(center, "upcoming", []) or [],
        key=lambda f: getattr(f, "kickoff_time", None) or getattr(f, "kickoff_utc", None),
    )
    for fixture in upcoming:
        if exclude_today and is_kickoff_today(fixture):
            continue
        return fixture
    return None


def _select_fixture(fixture_id: int) -> None:
    st.session_state["selected_fixture_id"] = fixture_id
    st.session_state["fixture_id"] = fixture_id
    st.session_state["gui_page"] = "predict"
    st.rerun()


def _render_today_card(
    fixture: Any,
    locale: Locale,
    *,
    key_prefix: str,
    on_predict: Callable[[int], None] | None,
) -> None:
    home = getattr(fixture, "home_team", "—")
    away = getattr(fixture, "away_team", "—")
    kickoff = getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None)
    local_ko, utc_ko = format_kickoff_times(kickoff)
    group = format_group_stage(fixture)
    status_key = _status_key(fixture)
    fid = _fixture_id(fixture)

    with st.container(border=True):
        st.markdown(f"**{home} vs {away}**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption(gui_t("card.kickoff_local", locale))
            st.markdown(f"**{local_ko}**")
        with c2:
            st.caption(gui_t("card.kickoff_utc", locale))
            st.markdown(f"**{utc_ko}**")
        with c3:
            st.caption(gui_t("card.group", locale))
            st.markdown(f"**{group}**")
        venue = getattr(fixture, "venue", None) or ""
        if venue and str(venue).strip() not in {"", "—", "TBD"}:
            st.caption(f"{gui_t('card.venue', locale)}: **{venue}**")
        render_status_badge(
            gui_t("status.live", locale) if status_key == "live" else (
                gui_t("status.finished", locale) if status_key == "finished" else gui_t("status.upcoming", locale)
            ),
            kind=gui_t("card.status", locale),
            locale=locale,
        )
        if status_key != "finished" and on_predict and fid:
            if st.button(gui_t("home.predict_match", locale), key=f"{key_prefix}_pred_{fid}", use_container_width=True):
                on_predict(fid)


def render_user_home_dashboard(
    locale: Locale,
    *,
    center: Any,
    api_ready: bool,
    last_prediction: Any | None,
    on_quick_predict: Callable[[], None] | None = None,
    goto_predict: Callable[[], None] | None = None,
    goto_reports: Callable[[], None] | None = None,
) -> None:
    """Today-only product dashboard — never raises."""
    try:
        _render(
            locale,
            center,
            api_ready,
            last_prediction,
            on_quick_predict,
            goto_predict,
            goto_reports,
        )
    except Exception:
        st.info(gui_t("home.user_welcome", locale))


def _render(
    locale: Locale,
    center: Any,
    api_ready: bool,
    last_prediction: Any | None,
    on_quick_predict: Callable[[], None] | None,
    goto_predict: Callable[[], None] | None,
    goto_reports: Callable[[], None] | None,
) -> None:
    st.markdown(f"### {gui_t('home.user_welcome', locale)}")
    st.caption(gui_t("home.today_subtitle", locale))

    live = list(getattr(center, "live", []) or [])
    today_matches = _today_fixtures(center)

    if live:
        st.markdown(f"#### {gui_t('home.live_now', locale)}")
        for fixture in live:
            _render_today_card(fixture, locale, key_prefix="home_live", on_predict=_select_fixture)

    st.markdown(f"#### {gui_t('home.today_matches', locale)}")
    if today_matches:
        for fixture in today_matches:
            if fixture in live:
                continue
            _render_today_card(fixture, locale, key_prefix="home_today", on_predict=_select_fixture)
    elif not live:
        nxt = _next_upcoming(center, exclude_today=False)
        if nxt:
            st.info(gui_t("home.no_match_today_next", locale))
            _render_today_card(nxt, locale, key_prefix="home_next", on_predict=_select_fixture)
        else:
            st.info(gui_t("no_fixture", locale))

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**{gui_t('home.last_prediction', locale)}**")
        if last_prediction and getattr(last_prediction, "success", False):
            pred = last_prediction.prediction
            st.metric(pred.match_name, f"{pred.one_x_two.selection} · {pred.over_under.selection}")
            st.caption(f"{gui_t('badge.confidence', locale)}: {pred.confidence_score:.0f}/100")
            if pred.first_goal and pred.first_goal.team:
                fg_band = pred.first_goal.minute_range or "—"
                st.caption(f"{gui_t('pro_card.first_goal_team', locale)}: {pred.first_goal.team} · {fg_band}")
        else:
            st.caption(gui_t("home.no_prediction_yet", locale))

    with col_b:
        st.markdown(f"**{gui_t('home.quota_status', locale)}**")
        try:
            from worldcup_predictor.access.identity import is_registered_user
            from worldcup_predictor.access.prediction_gate import preview_prediction_quota

            if is_registered_user():
                quota = preview_prediction_quota()
                st.caption(f"{gui_t('access.quota_line', locale).format(used=quota.used_today, limit=quota.daily_limit, remaining=quota.remaining or 0)}")
            else:
                st.caption(gui_t("access.panel_hint", locale))
        except Exception:
            st.caption(gui_t("home.system_status", locale))

    st.markdown(f"#### {gui_t('home.quick_actions', locale)}")
    q1, q2, q3 = st.columns(3)
    with q1:
        if st.button(gui_t("home.predict_today", locale), type="primary", use_container_width=True):
            target = today_matches[0] if today_matches else (live[0] if live else _next_upcoming(center, exclude_today=False))
            if target:
                _select_fixture(_fixture_id(target))
            elif goto_predict:
                goto_predict()
            elif on_quick_predict:
                on_quick_predict()
            else:
                st.session_state["gui_page"] = "predict"
                st.rerun()
    with q2:
        if st.button(gui_t("home.open_group_browser", locale), use_container_width=True):
            st.session_state["gui_page"] = "predict"
            st.session_state["gui_expand_group_browser"] = True
            st.rerun()
    with q3:
        if st.button(gui_t("home.open_reports", locale), use_container_width=True):
            if goto_reports:
                goto_reports()
            else:
                st.session_state["gui_page"] = "professional_reports"
                st.rerun()
