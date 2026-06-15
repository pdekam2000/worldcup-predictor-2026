"""Team name search with fuzzy matching over tournament fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Literal

from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.match_center import classify_status

MatchBucket = Literal["upcoming", "live", "finished"]


TEAM_ALIASES: dict[str, list[str]] = {
    "united states": ["usa", "u.s.a.", "us", "united states", "america"],
    "germany": ["germany", "deutschland"],
    "canada": ["canada"],
    "iran": ["iran", "ir iran", "islamic republic of iran"],
    "south korea": ["south korea", "korea republic", "korea, republic of", "republic of korea"],
    "czechia": ["czechia", "czech republic"],
    "mexico": ["mexico"],
    "england": ["england"],
    "france": ["france"],
    "brazil": ["brazil"],
    "argentina": ["argentina"],
    "paraguay": ["paraguay"],
}


@dataclass(frozen=True)
class TeamMatchSearchResult:
    fixture_id: int
    home_team: str
    away_team: str
    opponent: str
    kickoff_utc: datetime
    venue: str
    status: str
    bucket: MatchBucket
    home_goals: int | None
    away_goals: int | None
    is_home: bool
    source: str
    match_label: str


def _normalize_query(query: str) -> str:
    return query.strip().lower()


def _canonical_team(name: str) -> str:
    lowered = name.strip().lower()
    for canonical, aliases in TEAM_ALIASES.items():
        if lowered == canonical or lowered in aliases:
            return canonical
    return lowered


def _team_matches_query(team_name: str, query: str) -> bool:
    team_key = _canonical_team(team_name)
    query_key = _normalize_query(query)
    canonical_query = _canonical_team(query_key)

    if query_key in team_key or team_key in query_key:
        return True
    if canonical_query == team_key:
        return True
    for canonical, aliases in TEAM_ALIASES.items():
        if query_key in aliases or canonical_query == canonical:
            if team_key == canonical or team_key in aliases:
                return True
    ratio = SequenceMatcher(None, team_key, query_key).ratio()
    return ratio >= 0.72


def search_team_matches(
    fixtures: list[TournamentFixture],
    query: str,
    *,
    limit_per_bucket: int = 25,
) -> dict[MatchBucket, list[TeamMatchSearchResult]]:
    if not query.strip():
        return {"upcoming": [], "live": [], "finished": []}

    buckets: dict[MatchBucket, list[TeamMatchSearchResult]] = {
        "upcoming": [],
        "live": [],
        "finished": [],
    }

    for fixture in fixtures:
        home_hit = _team_matches_query(fixture.home_team, query)
        away_hit = _team_matches_query(fixture.away_team, query)
        if not home_hit and not away_hit:
            continue

        bucket = classify_status(fixture.status)
        is_home = home_hit
        opponent = fixture.away_team if is_home else fixture.home_team
        score = ""
        if fixture.home_goals is not None and fixture.away_goals is not None:
            score = f" ({fixture.home_goals}-{fixture.away_goals})"

        buckets[bucket].append(
            TeamMatchSearchResult(
                fixture_id=fixture.fixture_id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                opponent=opponent,
                kickoff_utc=fixture.kickoff_time,
                venue=fixture.venue,
                status=fixture.status,
                bucket=bucket,
                home_goals=fixture.home_goals,
                away_goals=fixture.away_goals,
                is_home=is_home,
                source=fixture.source,
                match_label=f"{fixture.home_team} vs {fixture.away_team}{score}",
            )
        )

    for bucket in buckets:
        buckets[bucket].sort(key=lambda row: row.kickoff_utc, reverse=(bucket == "finished"))
        buckets[bucket] = buckets[bucket][:limit_per_bucket]

    return buckets
