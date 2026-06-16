"""Shared fixture display helpers for GUI pages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t
from worldcup_predictor.ui.kickoff_timezone import format_kickoff_display, format_kickoff_times


def _non_empty(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "TBD":
        return None
    return text


def _field(obj: Any, name: str, default: object = None) -> object | None:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def format_group_stage(
    fixture: Any,
    tournament_context: dict[str, Any] | None = None,
    *,
    standings_group: str | None = None,
) -> str:
    """Format group / stage label for cards and headers.

    Priority:
    1. fixture.round (API league.round, e.g. \"Group Stage - 1\")
    2. fixture.stage (domain Fixture.league round alias)
    3. fixture.group when meaningful
    4. tournament_context round / group / stage / group_name
    5. standings group name
    """
    ctx = tournament_context or {}

    round_val = (
        _non_empty(_field(fixture, "round"))
        or _non_empty(_field(fixture, "stage"))
        or _non_empty(_field(ctx, "round"))
    )
    group_val = _non_empty(_field(fixture, "group")) or _non_empty(_field(ctx, "group"))
    stage_val = _non_empty(_field(ctx, "stage"))
    ctx_group = _non_empty(_field(ctx, "group_name")) or _non_empty(standings_group)

    if round_val:
        if group_val and group_val.upper() not in round_val.upper():
            return f"{round_val} · {group_val}"
        return round_val

    if group_val:
        if stage_val and stage_val.upper() not in group_val.upper():
            return f"{group_val} · {stage_val}"
        return group_val

    if stage_val:
        return stage_val

    if ctx_group:
        return ctx_group

    return "—"


def format_match_subtitle(fixture: Any, locale: Locale) -> str:
    """One-line match context for page headers."""
    gs = format_group_stage(fixture)
    if gs == "—":
        return ""
    return f"{gui_t('card.group', locale)}: {gs}"


def _fixture_kickoff(fixture: Any) -> datetime | None:
    raw = _field(fixture, "kickoff_time") or _field(fixture, "kickoff_utc")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        text = str(raw).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _fixture_status_label(status: str | None, locale: Locale) -> str:
    code = (status or "NS").upper()
    if code in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}:
        return gui_t("status.live", locale)
    if code in {"FT", "AET", "PEN", "FINISHED"}:
        return gui_t("status.finished", locale)
    return gui_t("status.upcoming", locale)


def format_kickoff_caption(fixture: Any | None, locale: Locale) -> str:
    """Single-line kickoff caption: user local · venue · UTC."""
    kickoff = _fixture_kickoff(fixture)
    city = _non_empty(_field(fixture, "city"))
    country = _non_empty(_field(fixture, "country"))
    display = format_kickoff_display(kickoff, venue_city=city, venue_country=country, locale=locale)
    parts = [f"{gui_t('kickoff.user_local', locale)}: {display.user_local}"]
    if display.venue_local and display.venue_label:
        parts.append(f"{display.venue_label}: {display.venue_local}")
    parts.append(f"UTC: {display.utc}")
    if display.venue_unavailable and kickoff:
        parts.append(gui_t("kickoff.venue_unavailable_short", locale))
    return " · ".join(parts)


def render_kickoff_panel(fixture: Any | None, locale: Locale) -> None:
    """Three-line kickoff: user local, venue local, UTC."""
    kickoff = _fixture_kickoff(fixture)
    city = _non_empty(_field(fixture, "city"))
    country = _non_empty(_field(fixture, "country"))
    display = format_kickoff_display(kickoff, venue_city=city, venue_country=country, locale=locale)
    st.markdown(
        f"""
<div class="glass-card kickoff-panel">
  <div><strong>{display.user_local_label}:</strong> {display.user_local}</div>
  {f'<div><strong>{display.venue_label}:</strong> {display.venue_local}</div>' if display.venue_local else ''}
  <div><strong>{gui_t('card.kickoff_utc', locale)}:</strong> {display.utc}</div>
  {f'<div class="kickoff-warn">{gui_t("kickoff.venue_unavailable", locale)}</div>' if display.venue_unavailable and kickoff else ''}
</div>
""",
        unsafe_allow_html=True,
    )


def render_fixture_summary_panel(fixture: Any | None, fixture_id: int | None, locale: Locale) -> None:
    """Match Prediction header — fixture metadata (no API calls)."""
    if fixture is None and fixture_id is None:
        st.info(gui_t("fixture.select_hint", locale))
        return
    home = _field(fixture, "home_team") or "—"
    away = _field(fixture, "away_team") or "—"
    fid = fixture_id or _field(fixture, "fixture_id") or _field(fixture, "id") or "—"
    kickoff = _fixture_kickoff(fixture)
    city = _non_empty(_field(fixture, "city"))
    country = _non_empty(_field(fixture, "country"))
    ko = format_kickoff_display(kickoff, venue_city=city, venue_country=country, locale=locale)
    local_ko = ko.user_local
    utc_ko = ko.utc
    venue_ko = ko.venue_local or "—"
    group_label = format_group_stage(fixture)
    league = (
        _non_empty(_field(fixture, "league"))
        or _non_empty(_field(fixture, "competition"))
        or "FIFA World Cup"
    )
    venue = _non_empty(_field(fixture, "venue")) or "—"
    city = _non_empty(_field(fixture, "city"))
    country = _non_empty(_field(fixture, "country"))
    location = " · ".join(x for x in (city, country) if x) or "—"
    round_stage = (
        _non_empty(_field(fixture, "round"))
        or _non_empty(_field(fixture, "stage"))
        or group_label
    )
    status = _fixture_status_label(_field(fixture, "status"), locale)
    source = _non_empty(_field(fixture, "source"))

    with st.container(border=True):
        st.markdown(f"### {home} vs {away}")
        fields: list[tuple[str, str]] = [
            ("card.fixture_id", str(fid)),
            ("kickoff.user_local", local_ko),
            ("kickoff.venue_local", venue_ko if not ko.venue_unavailable else gui_t("kickoff.venue_unavailable_short", locale)),
            ("card.kickoff_utc", utc_ko),
            ("card.league", league or "—"),
            ("card.group", group_label if group_label != "—" else "—"),
            ("card.venue", venue),
            ("card.location", location),
            ("card.status", status),
            ("card.round", round_stage or "—"),
        ]
        if source:
            fields.append(("card.source", source))
        render_fixture_meta_grid(locale, fields, columns=3)


def render_fixture_meta_grid(
    locale: Locale,
    fields: list[tuple[str, str]],
    *,
    columns: int = 4,
) -> None:
    """Render labeled metadata using Streamlit widgets — never inside button labels."""
    if not fields:
        return
    width = max(1, min(columns, len(fields)))
    for start in range(0, len(fields), width):
        row = fields[start : start + width]
        cols = st.columns(len(row))
        for col, (label_key, value) in zip(cols, row):
            with col:
                label = gui_t(label_key, locale) if label_key.startswith("card.") else label_key
                st.caption(label)
                st.markdown(f"**{value}**")


def render_match_card_shell(
    title: str,
    locale: Locale,
    fields: list[tuple[str, str]],
    *,
    subtitle: str | None = None,
) -> None:
    """Bordered match card shell with native Streamlit meta grid."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if subtitle:
            st.caption(subtitle)
        render_fixture_meta_grid(locale, fields)
