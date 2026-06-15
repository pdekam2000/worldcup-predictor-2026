"""Match Center — classify and enrich live / upcoming / finished fixtures."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Literal

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService

LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
UPCOMING_STATUSES = frozenset({"NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO"})

SourceLabel = Literal["Demo", "Live API"]


@dataclass(frozen=True)
class MatchCenterSnapshot:
    upcoming: list[TournamentFixture]
    live: list[TournamentFixture]
    finished: list[TournamentFixture]
    source_label: SourceLabel
    live_api_available: bool
    live_count: int
    finished_today_count: int
    upcoming_today_count: int


@dataclass(frozen=True)
class WorldCupOverview:
    live_matches: int
    finished_today: int
    upcoming_today: int
    average_data_quality: float
    api_health_label: str
    source_label: SourceLabel


def classify_status(status: str) -> Literal["upcoming", "live", "finished"]:
    code = (status or "NS").upper()
    if code in LIVE_STATUSES:
        return "live"
    if code in FINISHED_STATUSES:
        return "finished"
    return "upcoming"


def format_source_label(fixture: TournamentFixture) -> SourceLabel:
    if fixture.is_placeholder or fixture.source == "placeholder":
        return "Demo"
    return "Live API"


def resolve_default_fixture_id(settings: Settings, competition_key: str) -> tuple[int, SourceLabel]:
    """Prefer live API fixture IDs; fall back to demo 2026001."""
    from worldcup_predictor.schedule.opening_match import find_opening_fixture

    service = create_schedule_service(settings, competition_key=competition_key)
    opening = find_opening_fixture(service)
    if opening and not opening.is_placeholder:
        return opening.fixture_id, "Live API"
    upcoming = service.get_upcoming_matches(limit=1)
    if upcoming and not upcoming[0].is_placeholder:
        return upcoming[0].fixture_id, "Live API"
    return 2026001, "Demo"


def _is_today(kickoff: datetime) -> bool:
    return kickoff.date() == date.today()


def _count_red_cards(events: list[dict[str, Any]], home_team: str, away_team: str) -> tuple[int, int]:
    home_red = away_red = 0
    for event in events:
        if event.get("type") != "Card":
            continue
        detail = str(event.get("detail", "")).lower()
        if "red" not in detail:
            continue
        team_name = event.get("team", {}).get("name", "")
        if team_name.lower() == home_team.lower():
            home_red += 1
        elif team_name.lower() == away_team.lower():
            away_red += 1
    return home_red, away_red


def _goal_scorers(events: list[dict[str, Any]]) -> list[str]:
    scorers: list[str] = []
    for event in events:
        if event.get("type") != "Goal":
            continue
        player = event.get("player", {}).get("name", "Unknown")
        minute = event.get("time", {}).get("elapsed", "?")
        team = event.get("team", {}).get("name", "?")
        scorers.append(f"{minute}' {player} ({team})")
    return scorers


def _stats_summary(stats_items: list[dict[str, Any]], home_team: str) -> dict[str, str]:
    summary: dict[str, str] = {}
    for block in stats_items:
        team_name = block.get("team", {}).get("name", "")
        side = "home" if team_name.lower() == home_team.lower() else "away"
        for stat in block.get("statistics", []):
            stat_type = str(stat.get("type", ""))
            value = stat.get("value")
            if stat_type and value is not None:
                summary[f"{side}_{stat_type.lower().replace(' ', '_')}"] = str(value)
    return summary


def enrich_fixture(api: ApiFootballClient, fixture: TournamentFixture) -> TournamentFixture:
    """Attach events and statistics when API is configured."""
    if not api.is_configured or fixture.is_placeholder:
        return fixture

    events_result = api.get_fixture_events(fixture.fixture_id)
    events = events_result.data if events_result.ok and isinstance(events_result.data, list) else []
    home_red, away_red = _count_red_cards(events, fixture.home_team, fixture.away_team)
    scorers = _goal_scorers(events)

    stats_summary: dict[str, str] = {}
    if classify_status(fixture.status) == "finished":
        stats_result = api.get_fixture_statistics(fixture.fixture_id)
        if stats_result.ok and isinstance(stats_result.data, list):
            stats_summary = _stats_summary(stats_result.data, fixture.home_team)

    return replace(
        fixture,
        red_cards_home=home_red,
        red_cards_away=away_red,
        goal_scorers=scorers,
        stats_summary=stats_summary,
    )


def build_match_center(
    service: WorldCupScheduleService,
    settings: Settings,
    *,
    enrich_live: bool = True,
    enrich_finished_limit: int = 15,
) -> MatchCenterSnapshot:
    fixtures = service.get_all_worldcup_fixtures()
    live_api = any(not f.is_placeholder for f in fixtures)

    upcoming: list[TournamentFixture] = []
    live: list[TournamentFixture] = []
    finished: list[TournamentFixture] = []

    for fixture in sorted(fixtures, key=lambda f: f.kickoff_time):
        bucket = classify_status(fixture.status)
        if bucket == "upcoming":
            upcoming.append(fixture)
        elif bucket == "live":
            live.append(fixture)
        else:
            finished.append(fixture)

    upcoming.sort(key=lambda f: f.kickoff_time)
    live.sort(key=lambda f: f.kickoff_time)
    finished.sort(key=lambda f: f.kickoff_time, reverse=True)

    api = ApiFootballClient(settings)
    dedicated_live = service.get_live_fixtures_from_api() if api.is_configured else []
    if dedicated_live:
        live_ids = {f.fixture_id for f in dedicated_live}
        live = dedicated_live
        upcoming = [f for f in upcoming if f.fixture_id not in live_ids]
        live_api = True

    if enrich_live and api.is_configured:
        live = [enrich_fixture(api, f) for f in live]
        finished = [
            enrich_fixture(api, f) for f in finished[:enrich_finished_limit]
        ] + finished[enrich_finished_limit:]

    source: SourceLabel = "Live API" if live_api else "Demo"
    return MatchCenterSnapshot(
        upcoming=upcoming,
        live=live,
        finished=finished,
        source_label=source,
        live_api_available=live_api,
        live_count=len(live),
        finished_today_count=sum(1 for f in finished if _is_today(f.kickoff_time)),
        upcoming_today_count=sum(1 for f in upcoming if _is_today(f.kickoff_time)),
    )


def actual_result(home_goals: int | None, away_goals: int | None) -> str | None:
    if home_goals is None or away_goals is None:
        return None
    if home_goals == away_goals:
        return "draw"
    return "home_win" if home_goals > away_goals else "away_win"


def prediction_accuracy_status(
    prediction: MatchPrediction | None,
    fixture: TournamentFixture,
) -> str:
    actual = actual_result(fixture.home_goals, fixture.away_goals)
    if actual is None:
        return "unknown"
    if prediction is None:
        return "no_prediction"
    predicted = prediction.one_x_two.selection
    if predicted == actual:
        return "correct"
    return "incorrect"


def winner_label(fixture: TournamentFixture) -> str:
    actual = actual_result(fixture.home_goals, fixture.away_goals)
    if actual == "draw":
        return "Draw"
    if actual == "home_win":
        return fixture.home_team
    if actual == "away_win":
        return fixture.away_team
    return "—"
