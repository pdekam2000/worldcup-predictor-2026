"""Parse API-Football fixture payloads into TournamentFixture — shared Phase 39."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.domain.schedule import TournamentFixture

logger = logging.getLogger(__name__)

FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})


def extract_group_from_round(stage: str) -> str:
    import re

    match = re.search(r"Group\s+([A-H])\b", stage or "", re.IGNORECASE)
    if match:
        return f"Group {match.group(1).upper()}"
    return stage or "—"


def parse_api_fixture_item(item: dict[str, Any], *, source: str = "live") -> TournamentFixture | None:
    """Convert one API-Football fixtures response item to TournamentFixture."""
    try:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        league = item.get("league") or {}
        venue = fixture.get("venue") or {}
        kickoff_raw = fixture.get("date") or ""
        if not kickoff_raw:
            return None
        kickoff = (
            datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        venue_name = venue.get("name") or "TBD"
        city = venue.get("city") or "TBD"
        country = venue.get("country") or league.get("country") or "TBD"
        stage = league.get("round") or league.get("name") or "Regular Season"
        group = extract_group_from_round(str(stage))
        goals = item.get("goals") or {}
        score = item.get("score") or {}
        halftime = score.get("halftime") or {}
        status_obj = fixture.get("status") or {}
        home_goals = goals.get("home")
        away_goals = goals.get("away")
        ht_home = halftime.get("home")
        ht_away = halftime.get("away")
        elapsed = status_obj.get("elapsed")
        home_logo = (teams.get("home") or {}).get("logo")
        away_logo = (teams.get("away") or {}).get("logo")
        fid = int(fixture.get("id") or 0)
        if fid <= 0:
            return None
        scorers = _parse_goal_scorers(item.get("events") or [])
        home_meta = teams.get("home") or {}
        away_meta = teams.get("away") or {}
        try:
            home_team_id = int(home_meta.get("id")) if home_meta.get("id") is not None else None
        except (TypeError, ValueError):
            home_team_id = None
        try:
            away_team_id = int(away_meta.get("id")) if away_meta.get("id") is not None else None
        except (TypeError, ValueError):
            away_team_id = None
        try:
            league_id = int(league.get("id")) if league.get("id") is not None else None
        except (TypeError, ValueError):
            league_id = None
        try:
            season = int(league.get("season")) if league.get("season") is not None else None
        except (TypeError, ValueError):
            season = None
        return TournamentFixture(
            fixture_id=fid,
            kickoff_time=kickoff,
            home_team=home_meta.get("name") or "TBD",
            away_team=away_meta.get("name") or "TBD",
            home_team_logo=str(home_logo) if home_logo else None,
            away_team_logo=str(away_logo) if away_logo else None,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            league_id=league_id,
            season=season,
            venue=str(venue_name),
            city=str(city),
            country=str(country),
            group=group,
            round=str(stage),
            status=str(status_obj.get("short") or "NS"),
            is_placeholder=False,
            source=source,  # type: ignore[arg-type]
            home_goals=int(home_goals) if home_goals is not None else None,
            away_goals=int(away_goals) if away_goals is not None else None,
            halftime_home_goals=int(ht_home) if ht_home is not None else None,
            halftime_away_goals=int(ht_away) if ht_away is not None else None,
            elapsed_minute=int(elapsed) if elapsed is not None else None,
            goal_scorers=scorers,
        )
    except (TypeError, ValueError, KeyError):
        logger.exception("Failed to parse API fixture item")
        return None


def _parse_goal_scorers(events: list[Any]) -> list[str]:
    scorers: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type", "")).lower() != "goal":
            continue
        player = (event.get("player") or {}).get("name") or "Unknown"
        team = (event.get("team") or {}).get("name") or "?"
        minute = event.get("time", {}).get("elapsed")
        label = f"{minute}' {player} ({team})" if minute is not None else f"{player} ({team})"
        scorers.append(label)
    return scorers
