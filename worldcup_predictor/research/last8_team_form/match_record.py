"""Shared match record helpers for Last-8 profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Last8MatchRecord:
    fixture_id: int | None
    kickoff_utc: str
    competition_key: str
    home_team: str
    away_team: str
    goals_for: int
    goals_against: int
    is_home: bool
    opponent: str
    total_goals: int
    btts: bool
    over_2_5: bool
    clean_sheet: bool
    source: str
    competition_tier: str | None = None


def is_friendly_competition(competition_key: str) -> bool:
    key = str(competition_key or "").strip().lower()
    return any(p in key for p in ("friendly", "friendlies"))


def regulation_goals_from_row(row: dict[str, Any], *, team_name: str) -> tuple[int, int, bool] | None:
    """Return (goals_for, goals_against, is_home) using regulation semantics when available."""
    home = str(row.get("home_team") or "")
    away = str(row.get("away_team") or "")
    if team_name not in (home, away):
        return None

    reg_h = row.get("regulation_home_goals")
    reg_a = row.get("regulation_away_goals")
    if reg_h is not None and reg_a is not None:
        try:
            hg, ag = int(reg_h), int(reg_a)
        except (TypeError, ValueError):
            hg = ag = None
    else:
        hg = ag = None

    if hg is None or ag is None:
        try:
            hg = int(row.get("home_goals"))
            ag = int(row.get("away_goals"))
        except (TypeError, ValueError):
            return None

    if hg < 0 or ag < 0:
        return None

    is_home = home == team_name
    if is_home:
        return hg, ag, True
    return ag, hg, False


def classify_competition_quality(
    match_competition: str,
    target_competition: str,
) -> str:
    mc = str(match_competition or "").strip().lower()
    tc = str(target_competition or "").strip().lower()
    if is_friendly_competition(mc):
        return "friendly"
    if mc == tc:
        return "same_league"
    if mc and tc and mc.split("_")[0] == tc.split("_")[0]:
        return "same_competition_level"
    if "cup" in mc or "fa_" in mc or "copa" in mc:
        return "cup"
    if "champions" in mc or "europa" in mc or "conference" in mc:
        return "continental"
    if "world_cup" in mc or mc == "national_team":
        return "national_team"
    return "other"
