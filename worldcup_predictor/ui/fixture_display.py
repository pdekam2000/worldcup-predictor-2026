"""Shared fixture display helpers for GUI pages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def format_kickoff_times(kickoff: datetime | None) -> tuple[str, str]:
    if kickoff is None:
        return "—", "—"
    aware = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=timezone.utc)
    local = aware.astimezone().strftime("%d %b %Y %H:%M")
    utc = aware.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    return local, utc


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
