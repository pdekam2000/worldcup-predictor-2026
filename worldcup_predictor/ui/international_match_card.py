"""Phase 30 — International match hero cards with flags and premium layout."""

from __future__ import annotations

from typing import Any, Literal

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.fixture_display import format_group_stage
from worldcup_predictor.ui.fixture_list_helpers import is_kickoff_today, local_kickoff_time_display
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.team_display import team_flag_html

CardVariant = Literal["upcoming", "live", "finished"]


def _score_color(value: float) -> str:
    if value < 50:
        return "#ef4444"
    if value <= 70:
        return "#eab308"
    return "#22c55e"


def _status_badge(status: str, locale: Locale) -> tuple[str, str, str]:
    code = (status or "NS").upper()
    if code in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}:
        return gui_t("status.live", locale), "#f97316", "live"
    if code in {"FT", "AET", "PEN", "FINISHED"}:
        return gui_t("status.finished", locale), "#ef4444", "finished"
    return gui_t("status.upcoming", locale), "#22c55e", "scheduled"


def _parse_quality(value: float | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        try:
            num = float(text)
            return num * 100 if num <= 1.0 else num
        except ValueError:
            return None
    return value * 100 if value <= 1.0 else value


def _parse_confidence(value: float | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        try:
            return float(text)
        except ValueError:
            return None
    return value


def is_favorite(fixture_id: int) -> bool:
    favs = st.session_state.get("favorite_fixtures") or set()
    return int(fixture_id) in favs


def toggle_favorite(fixture_id: int) -> None:
    favs: set[int] = set(st.session_state.get("favorite_fixtures") or set())
    fid = int(fixture_id)
    if fid in favs:
        favs.discard(fid)
    else:
        favs.add(fid)
    st.session_state["favorite_fixtures"] = favs


def render_score_bar(label: str, score: float | None, *, icon: str = "", shield: bool = False) -> None:
    display_icon = "🛡" if shield else icon
    if score is None:
        st.markdown(
            f'<div class="imc-metric-label">{display_icon} {label}: <strong>—</strong></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="imc-progress-track"><div class="imc-progress-fill" style="width:0%;background:#E5E7EB;"></div></div>', unsafe_allow_html=True)
        return
    clamped = max(0.0, min(100.0, score))
    color = _score_color(clamped)
    st.markdown(
        f'<div class="imc-metric-label">{display_icon} {label} <strong>{clamped:.0f}/100</strong></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="imc-progress-track"><div class="imc-progress-fill" '
        f'style="width:{clamped:.0f}%;background:{color};"></div></div>',
        unsafe_allow_html=True,
    )


def render_international_match_card(
    fixture: Any,
    locale: Locale,
    *,
    variant: CardVariant = "upcoming",
    confidence: float | None = None,
    data_quality: float | None = None,
    prediction_subtitle: str | None = None,
    tournament_context: dict[str, Any] | None = None,
    key_prefix: str = "imc",
    show_favorite: bool = True,
    extra_footer: str | None = None,
) -> None:
    home = getattr(fixture, "home_team", "?")
    away = getattr(fixture, "away_team", "?")
    fid = getattr(fixture, "fixture_id", None) or getattr(fixture, "id", 0)
    status = getattr(fixture, "status", "NS")
    venue = getattr(fixture, "venue", "") or "—"
    kickoff = getattr(fixture, "kickoff_time", None) or getattr(fixture, "kickoff_utc", None)
    group_label = format_group_stage(fixture, tournament_context)

    country_hint = getattr(fixture, "country", None)
    home_flag = team_flag_html(home, fixture=fixture, side="home", country_hint=country_hint)
    away_flag = team_flag_html(away, fixture=fixture, side="away")

    is_today = is_kickoff_today(fixture)
    local_time_only = local_kickoff_time_display(fixture)

    home_goals = getattr(fixture, "home_goals", None)
    away_goals = getattr(fixture, "away_goals", None)
    if variant == "live" and home_goals is not None and away_goals is not None:
        center_text = f"{home_goals} – {away_goals}"
        center_sub = f"{getattr(fixture, 'elapsed_minute', None) or status}'"
        center_class = "imc-center-score live"
        if is_today:
            center_class += " imc-center-today"
    elif variant == "finished" and home_goals is not None and away_goals is not None:
        center_text = f"{home_goals} – {away_goals}"
        center_sub = gui_t("status.finished", locale)
        center_class = "imc-center-score finished"
        if is_today:
            center_class += " imc-center-today"
    elif variant == "upcoming":
        center_text = "🏆 ⚽ VS ⚽ 🏆"
        center_sub = ""
        center_class = "imc-center-vs"
        if is_today:
            center_class += " imc-center-today"
    else:
        center_text = "VS"
        center_sub = ""
        center_class = "imc-center-vs"

    status_label, status_color, status_kind = _status_badge(status, locale)
    conf_val = _parse_confidence(confidence)
    dq_val = _parse_quality(data_quality)

    fav_star = "⭐" if is_favorite(int(fid)) else "☆"

    if is_today:
        st.markdown('<div class="imc-today-marker"></div>', unsafe_allow_html=True)

    with st.container(border=True):
        top_left, top_star = st.columns([6, 1])
        with top_star:
            if show_favorite and fid:
                if st.button(fav_star, key=f"{key_prefix}_fav_{fid}", help="Bookmark match"):
                    toggle_favorite(int(fid))
                    st.rerun()

        st.markdown(
            f"""
<div class="imc-hero">
  <div class="imc-team imc-team-home">
    <div class="imc-flag">{home_flag}</div>
    <div class="imc-team-name">{home}</div>
  </div>
  <div class="{center_class}">
    {"<div class='imc-center-kickoff'>" + local_time_only + "</div>" if variant == "upcoming" else ("<div class='imc-today-kickoff'>" + local_time_only + "</div>" if is_today else "")}
    {"<div class='imc-center-kickoff-label'>" + gui_t("card.kickoff_local", locale) + "</div>" if variant == "upcoming" else ""}
    <div class="imc-center-main">{center_text}</div>
    {"<div class='imc-center-sub'>" + center_sub + "</div>" if center_sub else ""}
  </div>
  <div class="imc-team imc-team-away">
    <div class="imc-flag">{away_flag}</div>
    <div class="imc-team-name">{away}</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        badge_html = (
            f'<span class="imc-badge imc-badge-{status_kind}">● {status_label}</span>'
        )
        if is_today:
            badge_html += (
                '<span class="imc-badge imc-badge-today">⚽ TODAY</span>'
            )
        if group_label and group_label != "—":
            badge_html += (
                f'<span class="imc-badge imc-badge-stage">🏆 {group_label}</span>'
            )
        st.markdown(f'<div class="imc-badges">{badge_html}</div>', unsafe_allow_html=True)

        from worldcup_predictor.ui.kickoff_timezone import format_kickoff_display

        ko_display = format_kickoff_display(
            kickoff,
            venue_city=getattr(fixture, "city", None),
            venue_country=getattr(fixture, "country", None),
            locale=locale,
        )
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.caption(gui_t("kickoff.user_local", locale))
            st.markdown(f"**{ko_display.user_local}**")
        with m2:
            st.caption(gui_t("kickoff.venue_local", locale))
            if ko_display.venue_local:
                st.markdown(f"**{ko_display.venue_local}**")
            else:
                st.caption(gui_t("kickoff.venue_unavailable_short", locale))
        with m3:
            st.caption(gui_t("card.kickoff_utc", locale))
            st.markdown(f"**{ko_display.utc}**")
        with m4:
            st.caption(gui_t("card.venue", locale))
            st.markdown(f"**{venue}**")

        mc1, mc2 = st.columns(2)
        with mc1:
            render_score_bar(gui_t("card.confidence", locale), conf_val)
        with mc2:
            render_score_bar(gui_t("card.data_quality", locale), dq_val, shield=True)

        if prediction_subtitle:
            st.caption(prediction_subtitle)
        if extra_footer:
            st.caption(extra_footer)


def render_developer_panel(
    fixture: Any,
    *,
    locale: Locale,
    source: str | None = None,
    intel: Any | None = None,
) -> None:
    """Technical fixture details — hidden from main card flow."""
    fid = getattr(fixture, "fixture_id", None) or getattr(fixture, "id", "—")
    with st.expander(gui_t("dev.panel", locale), expanded=False):
        st.markdown(f"**{gui_t('card.fixture_id', locale)}:** `{fid}`")
        st.markdown(f"**Source:** `{source or getattr(fixture, 'source', '—')}`")
        st.markdown(f"**Status code:** `{getattr(fixture, 'status', '—')}`")
        if getattr(fixture, "stats_summary", None):
            st.json(dict(list(fixture.stats_summary.items())[:8]))

        if fid and fid != "—":
            try:
                from worldcup_predictor.ui.market_consensus_debug_panel import (
                    render_market_consensus_debug_panel,
                )

                st.divider()
                render_market_consensus_debug_panel(int(fid), locale, intel=intel)
            except Exception:
                st.caption(gui_t("dev.odds_audit_unavailable", locale).format(error="render failed"))
