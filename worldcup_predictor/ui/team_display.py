"""Team name + flag rendering helpers for match cards."""

from __future__ import annotations

import html
from typing import Any

from worldcup_predictor.ui.country_flags import flag_html_for_team


def _logo_for_side(fixture: Any | None, side: str) -> str | None:
    if fixture is None:
        return None
    key = f"{side}_team_logo"
    url = getattr(fixture, key, None)
    if url and str(url).startswith("http"):
        return str(url)
    return None


def team_flag_html(
    team_name: str,
    *,
    fixture: Any | None = None,
    side: str = "home",
    country_hint: str | None = None,
    logo_url: str | None = None,
) -> str:
    """Flag HTML only — safe when logo missing."""
    url = logo_url or _logo_for_side(fixture, side)
    try:
        return flag_html_for_team(team_name, country_hint=country_hint, logo_url=url)
    except Exception:
        return flag_html_for_team(team_name, country_hint=country_hint)


def team_with_flag_html(
    team_name: str,
    *,
    fixture: Any | None = None,
    side: str = "home",
    country_hint: str | None = None,
    logo_url: str | None = None,
) -> str:
    """Inline flag + escaped team name."""
    flag = team_flag_html(
        team_name,
        fixture=fixture,
        side=side,
        country_hint=country_hint,
        logo_url=logo_url,
    )
    safe = html.escape(team_name or "—")
    return f'<span class="team-with-flag">{flag}<span class="team-name-text">{safe}</span></span>'


def match_header_html(
    home: str,
    away: str,
    *,
    fixture: Any | None = None,
    country_hint: str | None = None,
) -> str:
    """[Flag] Home vs [Flag] Away — markdown-safe HTML block."""
    home_block = team_with_flag_html(
        home,
        fixture=fixture,
        side="home",
        country_hint=country_hint,
    )
    away_block = team_with_flag_html(away, fixture=fixture, side="away")
    return (
        f'<div class="match-header-flags">'
        f'{home_block}<span class="match-vs"> vs </span>{away_block}'
        f"</div>"
    )


def match_showcase_html(
    home: str,
    away: str,
    *,
    fixture: Any | None = None,
    country_hint: str | None = None,
) -> str:
    """Large flag showdown — dashboard hero cards."""
    home_flag = team_flag_html(
        home,
        fixture=fixture,
        side="home",
        country_hint=country_hint,
    )
    away_flag = team_flag_html(away, fixture=fixture, side="away")
    safe_home = html.escape(home or "—")
    safe_away = html.escape(away or "—")
    return f"""
<div class="match-showcase">
  <div class="match-showcase-team match-showcase-home">
    <div class="match-showcase-flag">{home_flag}</div>
    <div class="match-showcase-name">{safe_home}</div>
  </div>
  <div class="match-showcase-vs">VS</div>
  <div class="match-showcase-team match-showcase-away">
    <div class="match-showcase-flag">{away_flag}</div>
    <div class="match-showcase-name">{safe_away}</div>
  </div>
</div>
"""
