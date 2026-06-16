from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import WORLD_CUP_2026, CompetitionConfig
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.schedule import (
    GroupStanding,
    QualificationStatus,
    ScheduleHealthReport,
    ScheduleSource,
    TournamentFixture,
    TournamentOverview,
    UpcomingMatchWindow,
    WorldCupGroup,
)

logger = logging.getLogger(__name__)

_PLACEHOLDER_GROUP_TEAMS: dict[str, list[tuple[str, int, int, QualificationStatus]]] = {
    "Group A": [
        ("USA", 0, 0, "must_win"),
        ("Mexico", 0, 0, "must_win"),
        ("Colombia", 0, 0, "unknown"),
        ("Ecuador", 0, 0, "unknown"),
    ],
    "Group B": [
        ("Canada", 0, 0, "unknown"),
        ("Brazil", 0, 0, "likely_qualified"),
        ("Chile", 0, 0, "unknown"),
        ("Peru", 0, 0, "unknown"),
    ],
    "Group C": [
        ("Germany", 0, 0, "must_win"),
        ("Japan", 0, 0, "unknown"),
        ("South Korea", 0, 0, "unknown"),
        ("Australia", 0, 0, "unknown"),
    ],
    "Group D": [
        ("France", 0, 0, "likely_qualified"),
        ("Morocco", 0, 0, "unknown"),
        ("Denmark", 0, 0, "unknown"),
        ("Tunisia", 0, 0, "unknown"),
    ],
    "Group E": [
        ("England", 0, 0, "must_win"),
        ("Argentina", 0, 0, "likely_qualified"),
        ("Poland", 0, 0, "unknown"),
        ("Serbia", 0, 0, "unknown"),
    ],
    "Group F": [
        ("Spain", 0, 0, "likely_qualified"),
        ("Portugal", 0, 0, "must_win"),
        ("Croatia", 0, 0, "unknown"),
        ("Switzerland", 0, 0, "unknown"),
    ],
    "Group G": [
        ("Netherlands", 0, 0, "unknown"),
        ("Senegal", 0, 0, "unknown"),
        ("Costa Rica", 0, 0, "rotation_risk"),
        ("Wales", 0, 0, "eliminated"),
    ],
    "Group H": [
        ("Italy", 0, 0, "must_win"),
        ("Uruguay", 0, 0, "unknown"),
        ("Belgium", 0, 0, "likely_qualified"),
        ("Austria", 0, 0, "unknown"),
    ],
}

_VENUE_COUNTRY_HINTS: dict[str, str] = {
    "Rutherford": "USA",
    "Vancouver": "Canada",
    "Atlanta": "USA",
    "Inglewood": "USA",
    "Arlington": "USA",
    "Miami": "USA",
    "Philadelphia": "USA",
    "Santa Clara": "USA",
}


class WorldCupScheduleService:
    """World Cup 2026 fixture schedule and group table intelligence."""

    def __init__(
        self,
        settings: Settings,
        api_client: ApiFootballClient | None = None,
        competition: CompetitionConfig | None = None,
        supports_groups: bool | None = None,
        supports_table: bool | None = None,
        supports_knockout: bool | None = None,
    ) -> None:
        self._settings = settings
        self._api = api_client or ApiFootballClient(settings)
        self._competition = competition or WORLD_CUP_2026
        self._supports_groups = (
            supports_groups if supports_groups is not None else self._competition.supports_groups
        )
        self._supports_table = (
            supports_table if supports_table is not None else self._competition.supports_table
        )
        self._supports_knockout = (
            supports_knockout
            if supports_knockout is not None
            else self._competition.supports_knockout
        )
        self._fixtures_cache: list[TournamentFixture] | None = None
        self._groups_cache: dict[str, WorldCupGroup] | None = None
        self._health: ScheduleHealthReport | None = None

    def get_all_worldcup_fixtures(self) -> list[TournamentFixture]:
        if self._fixtures_cache is not None:
            return list(self._fixtures_cache)
        fixtures, health = self._load_fixtures()
        self._health = health
        self._fixtures_cache = fixtures
        return list(fixtures)

    def refresh_fixtures(self, *, force_api: bool = False) -> list[TournamentFixture]:
        """Clear in-memory cache and optionally bypass API file cache for fresh statuses."""
        self._fixtures_cache = None
        self._health = None
        if force_api and self._api.is_configured:
            result = self._api.get_all_fixtures_for_season(
                self._competition, force_refresh=True
            )
            if result.ok and result.data:
                parsed = [self._parse_api_fixture(item, result.source) for item in result.data]
                parsed = [p for p in parsed if p is not None]
                if parsed:
                    fixtures = sorted(parsed, key=lambda f: f.kickoff_time)
                    self._fixtures_cache = fixtures
                    self._health = ScheduleHealthReport(
                        source=result.source,  # type: ignore[arg-type]
                        is_placeholder=False,
                        warnings=[],
                        fixtures_count=len(fixtures),
                        standings_available=False,
                        groups_available=False,
                        api_configured=True,
                    )
                    return list(fixtures)
        return self.get_all_worldcup_fixtures()

    def get_live_fixtures_from_api(self) -> list[TournamentFixture]:
        """Dedicated live endpoint — 60–120s cache (Phase 53)."""
        if not self._api.is_configured:
            return []
        result = self._api.get_live_fixtures()
        if not result.ok or not isinstance(result.data, list):
            return []
        parsed = [self._parse_api_fixture(item, result.source) for item in result.data]
        return [p for p in parsed if p is not None]

    def get_upcoming_matches(self, limit: int = 5) -> list[TournamentFixture]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        upcoming = sorted(
            [f for f in self.get_all_worldcup_fixtures() if f.kickoff_time >= now],
            key=lambda f: f.kickoff_time,
        )
        return upcoming[:limit]

    def get_group_table(self, group_name: str) -> WorldCupGroup | None:
        groups = self._load_groups()
        key = group_name if group_name.startswith("Group") else f"Group {group_name.strip().upper()}"
        if key in groups:
            return groups[key]
        normalized = group_name.strip()
        for name, group in groups.items():
            if name.lower() == normalized.lower():
                return group
        return None

    def get_team_schedule(self, team_name: str) -> list[TournamentFixture]:
        needle = team_name.strip().lower()
        matches = [
            f
            for f in self.get_all_worldcup_fixtures()
            if f.home_team.lower() == needle or f.away_team.lower() == needle
        ]
        return sorted(matches, key=lambda f: f.kickoff_time)

    def get_tournament_overview(self) -> TournamentOverview:
        fixtures = self.get_all_worldcup_fixtures()
        groups = self._load_groups()
        health = self._health or ScheduleHealthReport()
        return TournamentOverview(
            fixtures=fixtures,
            groups=groups,
            health=health,
            upcoming=self.get_upcoming_matches(5),
        )

    def detect_next_betting_window(self) -> UpcomingMatchWindow:
        """Nearest analysis-ready window — not a betting recommendation."""
        upcoming = self.get_upcoming_matches(5)
        health = self._health or ScheduleHealthReport()
        warnings = list(health.warnings)
        if health.is_placeholder:
            warnings.append("Development placeholder schedule — analysis readiness limited.")
            score = 35.0
            ready = False
        elif not self._api.is_configured:
            score = 40.0
            ready = False
            warnings.append("API key not configured — using placeholder schedule data.")
        else:
            score = 72.0 if health.standings_available else 58.0
            ready = score >= 60
        if not upcoming:
            warnings.append("No upcoming fixtures found in schedule window.")
        return UpcomingMatchWindow(
            fixtures=upcoming,
            analysis_readiness_score=score,
            analysis_ready=ready,
            warnings=warnings,
            is_placeholder=health.is_placeholder,
            note="Analysis readiness window — not a betting recommendation.",
        )

    def _load_fixtures(self) -> tuple[list[TournamentFixture], ScheduleHealthReport]:
        warnings: list[str] = []
        source: ScheduleSource = "placeholder"
        is_placeholder = True
        if self._api.is_configured:
            result = self._api.get_all_fixtures_for_season(self._competition)
            if result.ok and result.data:
                parsed = [self._parse_api_fixture(item, result.source) for item in result.data]
                parsed = [p for p in parsed if p is not None]
                if parsed:
                    source = result.source  # type: ignore[assignment]
                    is_placeholder = False
                    health = ScheduleHealthReport(
                        source=source,
                        is_placeholder=False,
                        warnings=warnings,
                        fixtures_count=len(parsed),
                        standings_available=False,
                        groups_available=False,
                        api_configured=True,
                    )
                    return sorted(parsed, key=lambda f: f.kickoff_time), health
            warnings.append(f"Live fixtures unavailable ({result.error or 'empty'}) — using placeholders.")
        collection = self._api._placeholder_fixtures(self._competition, limit=8)  # noqa: SLF001
        fixtures = [self._from_domain_fixture(f) for f in collection.fixtures]
        warnings.append("Fixture dates and teams are development placeholders — unconfirmed.")
        if self._competition.key == WORLD_CUP_2026.key:
            warnings.append("World Cup 2026 API data may not be live yet — do not treat as official.")
        else:
            warnings.append(
                f"{self._competition.display_name} may use placeholders until live API data is available."
            )
        health = ScheduleHealthReport(
            source="placeholder",
            is_placeholder=True,
            warnings=warnings,
            fixtures_count=len(fixtures),
            standings_available=False,
            groups_available=self._supports_groups,
            api_configured=self._api.is_configured,
        )
        return fixtures, health

    def _load_groups(self) -> dict[str, WorldCupGroup]:
        if self._groups_cache is not None:
            return self._groups_cache
        if not self._supports_groups and not self._supports_table:
            if self._health:
                self._health.groups_available = False
                self._health.standings_available = False
                self._health.warnings.append(
                    f"Standings/table unavailable for {self._competition.display_name} "
                    f"({self._competition.compensation_type}) — not supported for this competition."
                )
            self._groups_cache = {}
            return {}
        if self._supports_table and not self._supports_groups:
            return self._load_league_table()
        warnings = self._health.warnings if self._health else []
        if self._api.is_configured:
            result = self._api.get_standings(self._competition)
            if result.ok and result.data:
                groups = self._parse_api_standings(result.data, result.source)
                if groups:
                    if self._health:
                        self._health.standings_available = True
                        self._health.groups_available = True
                    self._groups_cache = groups
                    return groups
            warnings.append("Live standings unavailable — using placeholder group tables.")
        if self._competition.key == WORLD_CUP_2026.key:
            groups = self._placeholder_groups()
        else:
            groups = {}
            warnings.append(
                f"No placeholder standings for {self._competition.display_name} — configure API key and league."
            )
        if self._health:
            self._health.groups_available = True
            self._health.warnings = list(dict.fromkeys(self._health.warnings + warnings))
        self._groups_cache = groups
        return groups

    def _parse_api_fixture(self, item: dict[str, Any], source: str) -> TournamentFixture | None:
        try:
            fixture = item.get("fixture", {})
            teams = item.get("teams", {})
            league = item.get("league", {})
            venue = fixture.get("venue", {}) or {}
            kickoff_raw = fixture.get("date", "")
            kickoff = (
                datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
            venue_name = venue.get("name") or "TBD"
            city = venue.get("city") or self._parse_city(venue_name)
            country = venue.get("country") or _VENUE_COUNTRY_HINTS.get(city, "TBD")
            stage = league.get("round") or "Group Stage"
            group = self._extract_group(stage)
            goals = item.get("goals", {}) or {}
            score = item.get("score", {}) or {}
            halftime = score.get("halftime") or {}
            status_obj = fixture.get("status", {}) or {}
            home_goals = goals.get("home")
            away_goals = goals.get("away")
            ht_home = halftime.get("home")
            ht_away = halftime.get("away")
            elapsed = status_obj.get("elapsed")
            home_logo = teams.get("home", {}).get("logo")
            away_logo = teams.get("away", {}).get("logo")
            return TournamentFixture(
                fixture_id=int(fixture.get("id", 0)),
                kickoff_time=kickoff,
                home_team=teams.get("home", {}).get("name", "TBD"),
                away_team=teams.get("away", {}).get("name", "TBD"),
                home_team_logo=str(home_logo) if home_logo else None,
                away_team_logo=str(away_logo) if away_logo else None,
                venue=venue_name,
                city=city,
                country=country,
                group=group,
                round=stage,
                status=status_obj.get("short", "NS"),
                is_placeholder=False,
                source=source,  # type: ignore[arg-type]
                home_goals=int(home_goals) if home_goals is not None else None,
                away_goals=int(away_goals) if away_goals is not None else None,
                halftime_home_goals=int(ht_home) if ht_home is not None else None,
                halftime_away_goals=int(ht_away) if ht_away is not None else None,
                elapsed_minute=int(elapsed) if elapsed is not None else None,
            )
        except (TypeError, ValueError, KeyError):
            logger.exception("Failed to parse API fixture")
            return None

    def _parse_api_standings(
        self,
        data: list[dict[str, Any]],
        source: str,
    ) -> dict[str, WorldCupGroup]:
        groups: dict[str, WorldCupGroup] = {}
        for block in data:
            league = block.get("league", {})
            group_name = league.get("group") or league.get("name") or "Group"
            if not str(group_name).startswith("Group"):
                group_name = f"Group {group_name}"
            rows: list[GroupStanding] = []
            for entry in block.get("standings", [[]])[0] if block.get("standings") else []:
                team = entry.get("team", {})
                all_stats = entry.get("all", {})
                goals = all_stats.get("goals", {})
                rows.append(
                    GroupStanding(
                        group_name=str(group_name),
                        team_name=team.get("name", "TBD"),
                        played=int(all_stats.get("played", 0)),
                        won=int(all_stats.get("win", 0)),
                        drawn=int(all_stats.get("draw", 0)),
                        lost=int(all_stats.get("lose", 0)),
                        goals_for=int(goals.get("for", 0)),
                        goals_against=int(goals.get("against", 0)),
                        goal_difference=int(entry.get("goalsDiff", 0)),
                        points=int(entry.get("points", 0)),
                        qualification_status=self._infer_qualification(
                            entry, int(entry.get("points", 0))
                        ),
                        rank=int(entry.get("rank", 0)),
                        is_placeholder=False,
                    )
                )
            groups[str(group_name)] = WorldCupGroup(
                group_name=str(group_name),
                standings=sorted(rows, key=lambda r: r.rank or 999),
                is_placeholder=False,
                source=source,  # type: ignore[arg-type]
                disclaimer="Live standings from API — verify against official sources.",
            )
        return groups

    def _load_league_table(self) -> dict[str, WorldCupGroup]:
        warnings = self._health.warnings if self._health else []
        label = f"{self._competition.display_name} Table"
        if self._api.is_configured:
            result = self._api.get_standings(self._competition)
            if result.ok and result.data:
                table = self._parse_league_table(result.data, result.source)
                if table:
                    if self._health:
                        self._health.standings_available = True
                        self._health.groups_available = False
                    self._groups_cache = {label: table}
                    return self._groups_cache
            warnings.append("Live league table unavailable — standings not returned from API.")
        if self._health:
            self._health.standings_available = False
            self._health.warnings = list(dict.fromkeys(self._health.warnings + warnings))
        self._groups_cache = {}
        return {}

    def _parse_league_table(
        self,
        data: list[dict[str, Any]],
        source: str,
    ) -> WorldCupGroup | None:
        rows: list[GroupStanding] = []
        label = f"{self._competition.display_name} Table"
        for block in data:
            entries = block.get("standings", [[]])[0] if block.get("standings") else []
            for entry in entries:
                team = entry.get("team", {})
                all_stats = entry.get("all", {})
                goals = all_stats.get("goals", {})
                rows.append(
                    GroupStanding(
                        group_name=label,
                        team_name=team.get("name", "TBD"),
                        played=int(all_stats.get("played", 0)),
                        won=int(all_stats.get("win", 0)),
                        drawn=int(all_stats.get("draw", 0)),
                        lost=int(all_stats.get("lose", 0)),
                        goals_for=int(goals.get("for", 0)),
                        goals_against=int(goals.get("against", 0)),
                        goal_difference=int(entry.get("goalsDiff", 0)),
                        points=int(entry.get("points", 0)),
                        qualification_status="unknown",
                        rank=int(entry.get("rank", 0)),
                        is_placeholder=False,
                    )
                )
        if not rows:
            return None
        return WorldCupGroup(
            group_name=label,
            standings=sorted(rows, key=lambda r: r.rank or 999),
            is_placeholder=False,
            source=source,  # type: ignore[arg-type]
            disclaimer="League table from API — informational only, verify against official sources.",
        )

    def _placeholder_groups(self) -> dict[str, WorldCupGroup]:
        groups: dict[str, WorldCupGroup] = {}
        for group_name, teams in _PLACEHOLDER_GROUP_TEAMS.items():
            standings = [
                GroupStanding(
                    group_name=group_name,
                    team_name=name,
                    played=0,
                    points=pts,
                    goal_difference=gd,
                    qualification_status=status,
                    rank=index + 1,
                    is_placeholder=True,
                )
                for index, (name, pts, gd, status) in enumerate(teams)
            ]
            groups[group_name] = WorldCupGroup(
                group_name=group_name,
                standings=standings,
                is_placeholder=True,
                source="placeholder",
                disclaimer="Placeholder group table — unconfirmed development data, not official.",
            )
        return groups

    def _from_domain_fixture(self, fixture: Fixture) -> TournamentFixture:
        city = self._parse_city(fixture.venue)
        country = _VENUE_COUNTRY_HINTS.get(city, "USA")
        group = self._extract_group(fixture.stage)
        return TournamentFixture(
            fixture_id=fixture.id,
            kickoff_time=fixture.kickoff_utc,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            venue=fixture.venue.split(",")[0].strip() if "," in fixture.venue else fixture.venue,
            city=city,
            country=country,
            group=group,
            round=fixture.stage,
            status=fixture.status,
            is_placeholder=True,
            source="placeholder",
        )

    @staticmethod
    def _parse_city(venue: str) -> str:
        if "," in venue:
            return venue.split(",")[-1].strip()
        return venue

    @staticmethod
    def _extract_group(stage: str) -> str:
        if not stage or stage.strip().upper() == "TBD":
            return "TBD"
        match = re.search(r"Group\s+([A-H])\b", stage, re.IGNORECASE)
        if match:
            return f"Group {match.group(1).upper()}"
        return stage.strip()

    @staticmethod
    def _infer_qualification(entry: dict[str, Any], points: int) -> QualificationStatus:
        desc = str(entry.get("description", "")).lower()
        if "eliminated" in desc:
            return "eliminated"
        if "qualified" in desc or points >= 7:
            return "likely_qualified"
        if points <= 2:
            return "must_win"
        return "unknown"
