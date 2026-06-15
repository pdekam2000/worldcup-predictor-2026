"""Live opening match discovery — synchronized with API-Football fixture statuses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService

LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_CLASSIFY = frozenset({"FT", "AET", "PEN"})

ReadinessLabel = Literal["Not Ready", "Partial", "Ready"]
StatusBadge = Literal["Upcoming", "Live", "Finished"]
OpeningMode = Literal["completed_opening", "active_opening", "next_match", "none"]

OPENING_TEAM_A = "mexico"
OPENING_TEAM_B = "south africa"
MIN_PREDICTION_QUALITY = 0.40

IGNORED_STATUSES = frozenset({"FT", "AET", "PEN", "CANC", "PST"})
ACTIVE_STATUSES = frozenset({"NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})

OPENING_CACHE_TTL_SECONDS = 300


def classify_status(status: str) -> Literal["upcoming", "live", "finished"]:
    code = (status or "NS").upper()
    if code in LIVE_STATUSES:
        return "live"
    if code in FINISHED_CLASSIFY:
        return "finished"
    return "upcoming"


@dataclass(frozen=True)
class OpeningMatchSnapshot:
    fixture: TournamentFixture
    intelligence: MatchIntelligenceReport | None
    readiness: ReadinessLabel
    readiness_score: float
    lineups_available: bool
    injuries_available: bool
    odds_available: bool
    weather_available: bool
    prediction_allowed: bool


@dataclass(frozen=True)
class OpeningMatchResolution:
    refreshed_at_utc: datetime
    mode: OpeningMode
    status_badge: StatusBadge
    opening_fixture: TournamentFixture | None
    display_fixture: TournamentFixture | None
    next_fixture: TournamentFixture | None
    opening_completed: bool


def _teams_match(fixture: TournamentFixture) -> bool:
    names = {fixture.home_team.strip().lower(), fixture.away_team.strip().lower()}
    return OPENING_TEAM_A in names and OPENING_TEAM_B in names


def _is_finished_status(status: str) -> bool:
    return status.upper() in FINISHED_STATUSES


def _is_ignored_for_next(status: str) -> bool:
    return status.upper() in IGNORED_STATUSES


def status_badge_for(fixture: TournamentFixture) -> StatusBadge:
    bucket = classify_status(fixture.status)
    if bucket == "finished" or _is_finished_status(fixture.status):
        return "Finished"
    if bucket == "live":
        return "Live"
    return "Upcoming"


def _find_opening_by_teams(fixtures: list[TournamentFixture]) -> TournamentFixture | None:
    for fixture in sorted(fixtures, key=lambda f: f.kickoff_time):
        if _teams_match(fixture):
            return fixture
    return None


def _find_next_active_fixture(
    fixtures: list[TournamentFixture],
    *,
    exclude_id: int | None = None,
) -> TournamentFixture | None:
    candidates: list[TournamentFixture] = []
    for fixture in fixtures:
        if exclude_id is not None and fixture.fixture_id == exclude_id:
            continue
        status = fixture.status.upper()
        if _is_ignored_for_next(status):
            continue
        if status in ACTIVE_STATUSES or classify_status(status) in ("upcoming", "live"):
            candidates.append(fixture)

    if not candidates:
        return None

    live = [f for f in candidates if classify_status(f.status) == "live"]
    if live:
        return sorted(live, key=lambda f: f.kickoff_time)[0]

    upcoming = [f for f in candidates if classify_status(f.status) == "upcoming"]
    if upcoming:
        return sorted(upcoming, key=lambda f: f.kickoff_time)[0]

    return sorted(candidates, key=lambda f: f.kickoff_time)[0]


def _maybe_enrich(settings: Settings, fixture: TournamentFixture) -> TournamentFixture:
    from worldcup_predictor.schedule.match_center import enrich_fixture

    api = ApiFootballClient(settings)
    if not api.is_configured or fixture.is_placeholder:
        return fixture
    bucket = classify_status(fixture.status)
    if bucket in ("live", "finished"):
        return enrich_fixture(api, fixture)
    return fixture


def resolve_opening_match(
    service: WorldCupScheduleService,
    settings: Settings,
    *,
    force_refresh: bool = True,
) -> OpeningMatchResolution:
    """Query live fixtures, detect opening match state, and offer next scheduled match."""
    fixtures = service.refresh_fixtures(force_api=force_refresh)
    refreshed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    opening = _find_opening_by_teams(fixtures)

    if opening and _is_finished_status(opening.status):
        enriched = _maybe_enrich(settings, opening)
        next_fixture = _find_next_active_fixture(fixtures, exclude_id=opening.fixture_id)
        return OpeningMatchResolution(
            refreshed_at_utc=refreshed_at,
            mode="completed_opening",
            status_badge="Finished",
            opening_fixture=enriched,
            display_fixture=enriched,
            next_fixture=next_fixture,
            opening_completed=True,
        )

    if opening and not _is_ignored_for_next(opening.status):
        enriched = _maybe_enrich(settings, opening)
        return OpeningMatchResolution(
            refreshed_at_utc=refreshed_at,
            mode="active_opening",
            status_badge=status_badge_for(enriched),
            opening_fixture=enriched,
            display_fixture=enriched,
            next_fixture=None,
            opening_completed=False,
        )

    next_fixture = _find_next_active_fixture(fixtures)
    if next_fixture:
        enriched = _maybe_enrich(settings, next_fixture)
        return OpeningMatchResolution(
            refreshed_at_utc=refreshed_at,
            mode="next_match",
            status_badge=status_badge_for(enriched),
            opening_fixture=opening,
            display_fixture=enriched,
            next_fixture=None,
            opening_completed=False,
        )

    return OpeningMatchResolution(
        refreshed_at_utc=refreshed_at,
        mode="none",
        status_badge="Upcoming",
        opening_fixture=opening,
        display_fixture=None,
        next_fixture=None,
        opening_completed=False,
    )


def find_opening_fixture(service: WorldCupScheduleService) -> TournamentFixture | None:
    """Prefer active Mexico vs South Africa; otherwise nearest non-finished fixture."""
    fixtures = service.get_all_worldcup_fixtures()
    opening = _find_opening_by_teams(fixtures)
    if opening and not _is_finished_status(opening.status):
        return opening
    return _find_next_active_fixture(fixtures)


def readiness_from_quality(score: float) -> ReadinessLabel:
    if score >= 0.65:
        return "Ready"
    if score >= 0.40:
        return "Partial"
    return "Not Ready"


def build_opening_snapshot(
    fixture: TournamentFixture,
    intelligence: MatchIntelligenceReport | None,
    settings: Settings,
) -> OpeningMatchSnapshot:
    quality = intelligence.data_quality.score if intelligence and intelligence.data_quality else 0.0
    readiness = readiness_from_quality(quality)
    available = set(intelligence.data_quality.available_fields) if intelligence and intelligence.data_quality else set()

    lineups = bool(
        intelligence
        and intelligence.lineups
        and intelligence.lineups.get("available")
    )
    injuries = "injuries" in available or bool(
        intelligence
        and (
            (intelligence.home_team.injuries and intelligence.home_team.injuries.players)
            or (intelligence.away_team.injuries and intelligence.away_team.injuries.players)
        )
    )
    odds = bool(intelligence and intelligence.odds and intelligence.odds.available)
    weather = settings.weather_configured

    return OpeningMatchSnapshot(
        fixture=fixture,
        intelligence=intelligence,
        readiness=readiness,
        readiness_score=quality,
        lineups_available=lineups,
        injuries_available=injuries,
        odds_available=odds,
        weather_available=weather,
        prediction_allowed=quality >= MIN_PREDICTION_QUALITY,
    )
