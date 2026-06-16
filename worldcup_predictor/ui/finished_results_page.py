"""Public Finished Results page — all completed matches with filters."""

from __future__ import annotations

from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.fixture_display import format_group_stage, format_kickoff_caption, format_kickoff_times
from worldcup_predictor.ui.gui_components import render_hero
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.professional_reports_page import list_exported_reports
from worldcup_predictor.ui.stored_prediction_summary import (
    evaluate_stored_prediction,
    get_latest_stored_prediction,
    render_stored_prediction_summary,
)


def _fixture_id(fixture: Any) -> int:
    return int(getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0) or 0)


def _kickoff_date(fixture: Any) -> str:
    kickoff = getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None)
    if kickoff is None:
        return ""
    try:
        if hasattr(kickoff, "date"):
            return kickoff.date().isoformat()
        text = str(kickoff)[:10]
        return text
    except Exception:
        return ""


def _score_text(fixture: Any) -> str:
    hg = getattr(fixture, "home_goals", None)
    ag = getattr(fixture, "away_goals", None)
    if hg is not None and ag is not None:
        return f"{hg}-{ag}"
    return "—"


def _has_export_report(fixture_id: int) -> bool:
    try:
        return any(item.fixture_id == fixture_id for item in list_exported_reports(limit=300))
    except Exception:
        return False


def _filter_options(finished: list[Any]) -> tuple[list[str], list[str], list[str]]:
    groups: set[str] = set()
    stages: set[str] = set()
    dates: set[str] = set()
    for fixture in finished:
        gs = format_group_stage(fixture)
        if gs and gs != "—":
            groups.add(gs)
        stage = getattr(fixture, "stage", None) or getattr(fixture, "round", None) or ""
        if stage:
            stages.add(str(stage))
        kick = _kickoff_date(fixture)
        if kick:
            dates.add(kick)
    return (
        sorted(groups),
        sorted(stages),
        sorted(dates, reverse=True),
    )


def render_finished_results_page(locale: Locale, *, center: Any) -> None:
    """Render finished matches table — never raises."""
    try:
        _render(locale, center)
    except Exception:
        st.warning(gui_t("finished_results.unavailable", locale))


def _render(locale: Locale, center: Any) -> None:
    render_hero(gui_t("nav.finished_results", locale), gui_t("finished_results.subtitle", locale))

    finished = sorted(
        list(getattr(center, "finished", []) or []),
        key=lambda f: getattr(f, "kickoff_time", None) or getattr(f, "kickoff_utc", None),
        reverse=True,
    )
    if not finished:
        st.info(gui_t("finished_results.empty", locale))
        return

    groups, stages, dates = _filter_options(finished)
    c1, c2, c3 = st.columns(3)
    with c1:
        group_filter = st.selectbox(
            gui_t("finished_results.filter_group", locale),
            [gui_t("finished_results.all_groups", locale)] + groups,
            key="fr_group_filter",
        )
    with c2:
        stage_filter = st.selectbox(
            gui_t("finished_results.filter_stage", locale),
            [gui_t("finished_results.all_stages", locale)] + stages,
            key="fr_stage_filter",
        )
    with c3:
        date_filter = st.selectbox(
            gui_t("finished_results.filter_date", locale),
            [gui_t("finished_results.all_dates", locale)] + dates,
            key="fr_date_filter",
        )

    all_groups_label = gui_t("finished_results.all_groups", locale)
    all_stages_label = gui_t("finished_results.all_stages", locale)
    all_dates_label = gui_t("finished_results.all_dates", locale)

    rows: list[Any] = []
    for fixture in finished:
        gs = format_group_stage(fixture)
        stage = str(getattr(fixture, "stage", None) or getattr(fixture, "round", None) or "")
        kick_date = _kickoff_date(fixture)
        if group_filter != all_groups_label and gs != group_filter:
            continue
        if stage_filter != all_stages_label and stage != stage_filter:
            continue
        if date_filter != all_dates_label and kick_date != date_filter:
            continue
        rows.append(fixture)

    st.caption(gui_t("finished_results.count", locale).format(count=len(rows)))

    for fixture in rows:
        _render_finished_row(fixture, locale)


def _render_finished_row(fixture: Any, locale: Locale) -> None:
    fid = _fixture_id(fixture)
    home = getattr(fixture, "home_team", "—")
    away = getattr(fixture, "away_team", "—")
    score = _score_text(fixture)
    status = getattr(fixture, "status", "FT")
    group = format_group_stage(fixture)
    ko_caption = format_kickoff_caption(fixture, locale)

    with st.container(border=True):
        st.markdown(
            f'<div class="match-row match-row-finished">'
            f'<span class="match-badge match-badge-finished">{gui_t("status.finished", locale)}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        col_a, col_b, col_c = st.columns([3, 2, 2])
        with col_a:
            st.markdown(f"**{home} {score} {away}**")
            st.caption(f"{group} · {ko_caption}")
        with col_b:
            st.caption(gui_t("card.status", locale))
            st.markdown(f"~~{status}~~" if status else gui_t("status.finished", locale))
        with col_c:
            btn_cols = st.columns(2)
            with btn_cols[0]:
                st.button(
                    gui_t("btn.predict_match", locale),
                    key=f"fr_pred_{fid}",
                    disabled=True,
                    use_container_width=True,
                    help=gui_t("finished_results.predict_disabled", locale),
                )
            with btn_cols[1]:
                if _has_export_report(fid):
                    if st.button(
                        gui_t("group_browser.view_report", locale),
                        key=f"fr_rep_{fid}",
                        use_container_width=True,
                    ):
                        st.session_state["gui_page"] = "professional_reports"
                        st.session_state["reports_filter_fixture_id"] = fid
                        st.rerun()

        stored = get_latest_stored_prediction(fid)
        if stored:
            evaluation = evaluate_stored_prediction(fid, fixture)
            render_stored_prediction_summary(
                fid,
                locale,
                compact=True,
                fixture=fixture,
                evaluation=evaluation,
            )
        elif _has_export_report(fid):
            st.caption(gui_t("finished_results.report_available", locale))
