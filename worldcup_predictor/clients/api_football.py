from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from worldcup_predictor.cache.api_cache import ApiCache, get_api_cache
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.competitions import CompetitionConfig
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import Fixture, FixtureCollection
from worldcup_predictor.quota.cache_policy import ttl_for_endpoint
from worldcup_predictor.quota.quota_tracker import get_quota_tracker
from worldcup_predictor.quota.request_throttle import ApiRequestThrottle

logger = logging.getLogger(__name__)

_throttle_lock = threading.Lock()
_throttle_singleton: ApiRequestThrottle | None = None


def _get_throttle(settings: Settings) -> ApiRequestThrottle:
    global _throttle_singleton
    with _throttle_lock:
        if _throttle_singleton is None:
            _throttle_singleton = ApiRequestThrottle(
                base_delay_seconds=settings.api_throttle_delay_seconds,
                warning_delay_seconds=settings.api_throttle_warning_delay_seconds,
                rate_limit_delay_seconds=settings.api_throttle_rate_limit_delay_seconds,
            )
        return _throttle_singleton


def _int_or_default(value: Any, default: int) -> int:
    """Coerce API scalar to int; use default when missing or invalid."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# Placeholder team IDs for offline development (not real API ids)
_PLACEHOLDER_TEAM_IDS: dict[str, int] = {
    "USA": 2380,
    "Mexico": 2289,
    "Canada": 2288,
    "Brazil": 2260,
    "Germany": 2250,
    "Japan": 2320,
    "France": 2240,
    "Morocco": 2310,
    "England": 2230,
    "Argentina": 2270,
    "Spain": 2220,
    "Portugal": 2290,
    "Netherlands": 2300,
    "Senegal": 2330,
    "Italy": 2210,
    "Uruguay": 2340,
}


class ApiFootballClient:
    """
    Placeholder-ready client for API-Football (api-sports.io).

    When API_FOOTBALL_KEY is set, calls live endpoints with TTL caching.
    Otherwise returns structured placeholder data for development.
    """

    def __init__(
        self,
        settings: Settings,
        cache: ApiCache | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = settings.api_football_base_url.rstrip("/")
        self._cache = cache or get_api_cache(
            settings.api_cache_dir,
            settings.api_cache_ttl_seconds,
        )

    @property
    def is_configured(self) -> bool:
        return self._settings.api_football_configured

    # ------------------------------------------------------------------ #
    # Phase 1 — fixtures list (unchanged behaviour)
    # ------------------------------------------------------------------ #

    def fetch_upcoming_fixtures(
        self,
        competition: CompetitionConfig,
        limit: int = 5,
    ) -> FixtureCollection:
        if self.is_configured:
            result = self._safe_get(
                "fixtures",
                {**competition.fixture_query_params(), "next": limit},
                placeholder_factory=lambda: None,
            )
            if result.ok and isinstance(result.data, list) and result.data:
                fixtures = [
                    self._parse_fixture(item, competition)
                    for item in result.data
                ]
                fixtures = sorted(fixtures, key=lambda f: f.kickoff_utc)[:limit]
                return FixtureCollection(
                    fixtures=fixtures,
                    competition_key=competition.key,
                    source="api-football",
                    is_placeholder=False,
                )
            logger.warning(
                "Live fixtures fetch failed or empty (%s); using placeholders",
                result.error,
            )
        return self._placeholder_fixtures(competition, limit)

    # ------------------------------------------------------------------ #
    # Phase 2 — intelligence endpoints
    # ------------------------------------------------------------------ #

    def get_fixture_by_id(self, fixture_id: int) -> ApiCallResult:
        return self._safe_get(
            "fixtures",
            {"id": fixture_id},
            placeholder_factory=lambda: self._placeholder_fixture_payload(fixture_id),
        )

    def get_team_statistics(
        self,
        team_id: int,
        league_id: int,
        season: int,
    ) -> ApiCallResult:
        return self._safe_get(
            "teams/statistics",
            {"team": team_id, "league": league_id, "season": season},
            placeholder_factory=lambda: self._placeholder_team_statistics(team_id),
        )

    def get_head_to_head(self, team_a_id: int, team_b_id: int, last: int = 5) -> ApiCallResult:
        h2h = f"{team_a_id}-{team_b_id}"
        return self._safe_get(
            "fixtures/headtohead",
            {"h2h": h2h, "last": last},
            placeholder_factory=lambda: self._placeholder_h2h(team_a_id, team_b_id, last),
        )

    def get_fixture_events(self, fixture_id: int) -> ApiCallResult:
        return self._safe_get(
            "fixtures/events",
            {"fixture": fixture_id},
            placeholder_factory=lambda: self._placeholder_events(fixture_id),
        )

    def get_fixture_statistics(self, fixture_id: int) -> ApiCallResult:
        return self._safe_get(
            "fixtures/statistics",
            {"fixture": fixture_id},
            placeholder_factory=lambda: self._placeholder_fixture_statistics(fixture_id),
        )

    def get_fixture_lineups(self, fixture_id: int) -> ApiCallResult:
        return self._safe_get(
            "fixtures/lineups",
            {"fixture": fixture_id},
            placeholder_factory=lambda: self._placeholder_lineups(fixture_id),
        )

    def get_injuries(
        self,
        fixture_id: int,
        league_id: int | None = None,
        season: int | None = None,
        *,
        force_refresh: bool = False,
    ) -> ApiCallResult:
        valid_league = int(league_id) if league_id is not None and int(league_id) > 0 else None
        valid_season = int(season) if season is not None and int(season) > 0 else None

        if valid_league is None:
            return self._injuries_skip_result(fixture_id, force_refresh=force_refresh)

        params: dict[str, Any] = {"fixture": fixture_id, "league": valid_league}
        if valid_season is not None:
            params["season"] = valid_season
        return self._safe_get(
            "injuries",
            params,
            placeholder_factory=lambda: self._placeholder_injuries(fixture_id),
            force_refresh=force_refresh,
        )

    def _injuries_skip_result(self, fixture_id: int, *, force_refresh: bool = False) -> ApiCallResult:
        """Skip injuries API when league_id is unknown — cache the skip to avoid repeat attempts."""
        from worldcup_predictor.quota.cache_policy import INJURIES_TTL_SECONDS

        tracker = get_quota_tracker()
        skip_endpoint = "injuries/skip"
        skip_params = {"fixture": fixture_id, "reason": "missing_league_id"}
        cache_key = ApiCache.build_key(skip_endpoint, skip_params)

        if not force_refresh:
            sqlite_cached = self._sqlite_cache_get(cache_key)
            if sqlite_cached is not None:
                tracker.record_cache_hit()
                return ApiCallResult(
                    data=sqlite_cached,
                    source="cache",
                    endpoint="injuries",
                    from_cache=True,
                    skip_reason="missing_league_id",
                )
            cached = self._cache.get(skip_endpoint, skip_params)
            if cached is not None:
                tracker.record_cache_hit()
                self._sqlite_cache_set(cache_key, skip_endpoint, skip_params, cached, INJURIES_TTL_SECONDS)
                return ApiCallResult(
                    data=cached,
                    source="cache",
                    endpoint="injuries",
                    from_cache=True,
                    skip_reason="missing_league_id",
                )

        tracker.record_local_hit()
        payload: list[Any] = []
        self._cache.set(skip_endpoint, skip_params, payload, ttl_seconds=INJURIES_TTL_SECONDS)
        self._sqlite_cache_set(cache_key, skip_endpoint, skip_params, payload, INJURIES_TTL_SECONDS)
        return ApiCallResult(
            data=payload,
            source="local",
            endpoint="injuries",
            skip_reason="missing_league_id",
        )

    def get_odds(self, fixture_id: int) -> ApiCallResult:
        return self._safe_get(
            "odds",
            {"fixture": fixture_id},
            placeholder_factory=lambda: self._placeholder_odds(fixture_id),
        )

    def get_team_recent_fixtures(self, team_id: int, last: int = 10) -> ApiCallResult:
        return self._safe_get(
            "fixtures",
            {"team": team_id, "last": last},
            placeholder_factory=lambda: self._placeholder_recent_fixtures(team_id, last),
        )

    # ------------------------------------------------------------------ #
    # Phase 6 — schedule / standings
    # ------------------------------------------------------------------ #

    def get_standings(self, competition: CompetitionConfig) -> ApiCallResult:
        return self._safe_get(
            "standings",
            competition.fixture_query_params(),
            placeholder_factory=lambda: None,
        )

    def get_all_fixtures_for_season(
        self,
        competition: CompetitionConfig,
        *,
        force_refresh: bool = False,
        sync_mode: str | None = None,
    ) -> ApiCallResult:
        from worldcup_predictor.quota.sync_modes import fixture_query_params_for_mode, normalize_sync_mode

        params = fixture_query_params_for_mode(
            competition.fixture_query_params(),
            normalize_sync_mode(sync_mode or self._settings.api_sync_mode),
        )
        return self._safe_get(
            "fixtures",
            params,
            placeholder_factory=lambda: None,
            force_refresh=force_refresh,
        )

    # ------------------------------------------------------------------ #
    # Phase 9 — historical import
    # ------------------------------------------------------------------ #

    def get_historical_fixtures(
        self,
        *,
        league_id: int | None = None,
        season: int | None = None,
        team_id: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
    ) -> ApiCallResult:
        """Fetch completed fixtures for backtest CSV import (no placeholder data)."""
        params: dict[str, Any] = {}
        if league_id is not None:
            params["league"] = league_id
        if season is not None:
            params["season"] = season
        if team_id is not None:
            params["team"] = team_id
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if status:
            params["status"] = status
        return self._safe_get(
            "fixtures",
            params,
            placeholder_factory=lambda: None,
        )

    # ------------------------------------------------------------------ #
    # Phase 53 — deep integration endpoints
    # ------------------------------------------------------------------ #

    def get_live_fixtures(self) -> ApiCallResult:
        """Live fixtures only — short TTL to avoid full season scans."""
        return self._safe_get(
            "fixtures",
            {"live": "all"},
            placeholder_factory=lambda: [],
            ttl_seconds=90,
        )

    def get_top_scorers(self, league_id: int, season: int) -> ApiCallResult:
        return self._safe_get(
            "players/topscorers",
            {"league": league_id, "season": season},
            placeholder_factory=lambda: [],
            ttl_seconds=86400,
        )

    def get_fixture_players(
        self,
        fixture_id: int,
        *,
        ttl_seconds: int = 1800,
    ) -> ApiCallResult:
        return self._safe_get(
            "fixtures/players",
            {"fixture": fixture_id},
            placeholder_factory=lambda: [],
            ttl_seconds=ttl_seconds,
        )

    def get_team_squad(self, team_id: int) -> ApiCallResult:
        return self._safe_get(
            "players/squads",
            {"team": team_id},
            placeholder_factory=lambda: [],
            ttl_seconds=604800,
        )

    def get_predictions(self, fixture_id: int) -> ApiCallResult:
        """API-Football predictions — reference only; empty if plan unavailable."""
        return self._safe_get(
            "predictions",
            {"fixture": fixture_id},
            placeholder_factory=lambda: [],
            ttl_seconds=3600,
        )

    def get_sidelined(
        self,
        *,
        fixture_id: int | None = None,
        team_id: int | None = None,
        player_id: int | None = None,
        probe_only: bool = False,
    ) -> ApiCallResult:
        """Sidelined/suspensions — team or player scoped (fixture param not supported by API)."""
        params: dict[str, Any] = {}
        if team_id is not None:
            params["team"] = team_id
        if player_id is not None:
            params["player"] = player_id
        if not params:
            return ApiCallResult(data=[], source="placeholder", endpoint="sidelined", error="team_id or player_id required")
        ttl = 60 if probe_only else 21600
        return self._safe_get(
            "sidelined",
            params,
            placeholder_factory=lambda: [],
            ttl_seconds=ttl,
        )

    # ------------------------------------------------------------------ #
    # Internal request + cache layer
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        return {
            "x-apisports-key": self._settings.api_football_key,
            "Accept": "application/json",
        }

    def _safe_get(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        placeholder_factory: Callable[[], Any],
        force_refresh: bool = False,
        ttl_seconds: int | None = None,
    ) -> ApiCallResult:
        if not self.is_configured:
            return ApiCallResult(
                data=placeholder_factory(),
                source="placeholder",
                endpoint=endpoint,
            )

        tracker = get_quota_tracker()
        effective_ttl = ttl_for_endpoint(endpoint, override=ttl_seconds)
        cache_key = ApiCache.build_key(endpoint, params)

        # Local-first for single-fixture lookups
        local_payload = self._local_first_payload(endpoint, params)
        if local_payload is not None and not force_refresh:
            tracker.record_local_hit()
            return ApiCallResult(
                data=local_payload,
                source="local",
                endpoint=endpoint,
                from_cache=True,
            )

        if not force_refresh:
            sqlite_cached = self._sqlite_cache_get(cache_key)
            if sqlite_cached is not None:
                tracker.record_cache_hit()
                return ApiCallResult(
                    data=sqlite_cached,
                    source="cache",
                    endpoint=endpoint,
                    from_cache=True,
                )

            cached = self._cache.get(endpoint, params)
            if cached is not None:
                tracker.record_cache_hit()
                self._sqlite_cache_set(cache_key, endpoint, params, cached, effective_ttl)
                return ApiCallResult(
                    data=cached,
                    source="cache",
                    endpoint=endpoint,
                    from_cache=True,
                )

        try:
            throttle = _get_throttle(self._settings)

            def _do_fetch() -> list[Any]:
                payload = self._fetch_raw(endpoint, params)
                return payload.get("response", [])

            response_items = throttle.execute(_do_fetch, quota_tracker=tracker)
            tracker.record_live()
            self._cache.set(endpoint, params, response_items, ttl_seconds=effective_ttl)
            self._sqlite_cache_set(cache_key, endpoint, params, response_items, effective_ttl)
            return ApiCallResult(
                data=response_items,
                source="live",
                endpoint=endpoint,
            )
        except Exception as exc:
            logger.exception("API-Football %s failed", endpoint)
            return ApiCallResult(
                data=placeholder_factory(),
                source="placeholder",
                endpoint=endpoint,
                error=str(exc),
            )

    def _local_first_payload(self, endpoint: str, params: dict[str, Any]) -> Any | None:
        if endpoint != "fixtures" or "id" not in params:
            return None
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository
            from worldcup_predictor.quota.local_first import load_fixture_api_item_from_db

            fixture_id = int(params["id"])
            repo = FootballIntelligenceRepository()
            if not repo.fixture_exists(fixture_id):
                return None
            return load_fixture_api_item_from_db(repo, fixture_id)
        except Exception:
            return None

    def _sqlite_cache_get(self, cache_key: str) -> Any | None:
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            return FootballIntelligenceRepository().get_api_cache_payload(cache_key)
        except Exception:
            return None

    def _sqlite_cache_set(
        self,
        cache_key: str,
        endpoint: str,
        params: dict[str, Any],
        payload: Any,
        ttl_seconds: int,
    ) -> None:
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            expires = (
                datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=ttl_seconds)
            ).isoformat()
            FootballIntelligenceRepository().set_api_cache_payload(
                cache_key=cache_key,
                endpoint=endpoint,
                params=params,
                payload=payload,
                expires_at=expires,
            )
        except Exception:
            pass

    def _fetch_raw(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=self._headers(), params=params)
            if response.status_code == 429:
                raise RuntimeError(f"API-Football HTTP 429 rate limit: {endpoint}")
            response.raise_for_status()
            payload = response.json()

        errors = payload.get("errors")
        if errors:
            err_text = str(errors).lower()
            if "429" in err_text or "rate limit" in err_text or "request limit" in err_text:
                raise RuntimeError(f"API-Football rate limit: {errors}")
            raise RuntimeError(f"API-Football error: {errors}")
        return payload

    def _parse_fixture(
        self,
        item: dict[str, Any],
        competition: CompetitionConfig,
    ) -> Fixture:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        league = item.get("league", {})
        venue = fixture.get("venue", {}) or {}

        kickoff_raw = fixture.get("date", "")
        kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))

        home = teams.get("home", {})
        away = teams.get("away", {})

        return Fixture(
            id=int(fixture.get("id", 0)),
            competition_key=competition.key,
            home_team=home.get("name", "TBD"),
            away_team=away.get("name", "TBD"),
            kickoff_utc=kickoff.astimezone(timezone.utc).replace(tzinfo=None),
            venue=venue.get("name") or "TBD",
            stage=league.get("round") or "Group Stage",
            league_id=_int_or_default(league.get("id"), competition.league_id),
            season=_int_or_default(league.get("season"), competition.season),
            status=fixture.get("status", {}).get("short", "NS"),
            source="api-football",
            home_team_id=home.get("id"),
            away_team_id=away.get("id"),
        )

    def parse_fixture_item(
        self,
        item: dict[str, Any],
        competition_key: str = "world_cup_2026",
    ) -> Fixture:
        league = item.get("league") or {}
        league_name = str(league.get("name") or "").strip() or "Unknown League"
        league_id = _int_or_default(league.get("id"), 0)
        season = _int_or_default(league.get("season"), 2026)
        return self._parse_fixture(
            item,
            CompetitionConfig(
                key=competition_key,
                name=league_name,
                league_id=league_id,
                season=season,
            ),
        )

    # ------------------------------------------------------------------ #
    # Placeholder payloads
    # ------------------------------------------------------------------ #

    def _placeholder_fixtures(
        self,
        competition: CompetitionConfig,
        limit: int,
    ) -> FixtureCollection:
        placeholders = [
            ("USA", "Mexico", "MetLife Stadium, East Rutherford", "Group A — Matchday 1", "Michael Oliver"),
            ("Canada", "Brazil", "BC Place, Vancouver", "Group B — Matchday 1", "Szymon Marciniak"),
            ("Germany", "Japan", "Mercedes-Benz Stadium, Atlanta", "Group C — Matchday 1", "Clement Turpin"),
            ("France", "Morocco", "SoFi Stadium, Inglewood", "Group D — Matchday 1", "Slavko Vincic"),
            ("England", "Argentina", "AT&T Stadium, Arlington", "Group E — Matchday 1", "Daniele Orsato"),
            ("Spain", "Portugal", "Hard Rock Stadium, Miami", "Group F — Matchday 1", "Anthony Taylor"),
            ("Netherlands", "Senegal", "Lincoln Financial Field, Philadelphia", "Group G — Matchday 1", "Danny Makkelie"),
            ("Italy", "Uruguay", "Levi's Stadium, Santa Clara", "Group H — Matchday 1", "Ivan Barton"),
        ]

        base_id = 2026000
        base_date = datetime(2026, 6, 11, 18, 0, 0)

        fixtures: list[Fixture] = []
        for index, (home, away, venue, stage, referee) in enumerate(placeholders[:limit]):
            kickoff = base_date.replace(day=11 + index)
            fixtures.append(
                Fixture(
                    id=base_id + index + 1,
                    competition_key=competition.key,
                    home_team=home,
                    away_team=away,
                    kickoff_utc=kickoff,
                    venue=venue,
                    stage=stage,
                    league_id=competition.league_id,
                    season=competition.season,
                    status="NS",
                    source="placeholder",
                    home_team_id=_PLACEHOLDER_TEAM_IDS.get(home),
                    away_team_id=_PLACEHOLDER_TEAM_IDS.get(away),
                    referee=referee,
                )
            )

        return FixtureCollection(
            fixtures=fixtures,
            competition_key=competition.key,
            source="placeholder",
            is_placeholder=True,
        )

    def resolve_placeholder_fixture(self, fixture_id: int) -> Fixture | None:
        return self._placeholder_fixture_by_id(fixture_id)

    def _placeholder_fixture_by_id(self, fixture_id: int) -> Fixture | None:
        collection = self._placeholder_fixtures(
            CompetitionConfig(
                key="world_cup_2026",
                name="FIFA World Cup 2026",
                league_id=1,
                season=2026,
            ),
            limit=8,
        )
        for fixture in collection.fixtures:
            if fixture.id == fixture_id:
                return fixture
        return None

    def _placeholder_fixture_payload(self, fixture_id: int) -> list[dict[str, Any]]:
        fixture = self._placeholder_fixture_by_id(fixture_id)
        if fixture is None:
            return []
        return [
            {
                "fixture": {
                    "id": fixture.id,
                    "date": fixture.kickoff_utc.isoformat() + "Z",
                    "venue": {"name": fixture.venue},
                    "status": {"short": fixture.status},
                },
                "teams": {
                    "home": {"id": fixture.home_team_id, "name": fixture.home_team},
                    "away": {"id": fixture.away_team_id, "name": fixture.away_team},
                },
                "league": {
                    "id": fixture.league_id,
                    "season": fixture.season,
                    "round": fixture.stage,
                },
            }
        ]

    def _placeholder_team_statistics(self, team_id: int) -> list[dict[str, Any]]:
        seed = team_id % 5
        forms = ["WWDLW", "WDWLL", "LWWDD", "WLWDW", "DWWLW"]
        avg_for = round(1.1 + (team_id % 9) * 0.12, 1)
        avg_against = round(0.7 + (team_id % 7) * 0.11, 1)
        return [
            {
                "team": {"id": team_id},
                "form": forms[seed],
                "fixtures": {
                    "played": {"total": 5, "home": 3, "away": 2},
                    "wins": {"total": 2 + seed % 2, "home": 1, "away": 1},
                    "draws": {"total": 1, "home": 0, "away": 1},
                    "loses": {"total": 1, "home": 1, "away": 0},
                },
                "goals": {
                    "for": {"total": {"total": int(avg_for * 5), "average": str(avg_for)}},
                    "against": {"total": {"total": int(avg_against * 5), "average": str(avg_against)}},
                },
            }
        ]

    def _placeholder_recent_fixtures(self, team_id: int, last: int) -> list[dict[str, Any]]:
        meetings = min(last, 5)
        results: list[dict[str, Any]] = []
        for i in range(meetings):
            home_id = team_id if i % 2 == 0 else 10000 + (team_id % 500)
            away_id = 10000 + (team_id % 500) if i % 2 == 0 else team_id
            home_g = 1 + ((team_id + i) % 3)
            away_g = (team_id + i * 2) % 3
            results.append(
                {
                    "fixture": {"id": 880000 + team_id * 10 + i},
                    "teams": {"home": {"id": home_id}, "away": {"id": away_id}},
                    "goals": {"home": home_g, "away": away_g},
                }
            )
        return results

    def _placeholder_h2h(
        self,
        team_a_id: int,
        team_b_id: int,
        last: int,
    ) -> list[dict[str, Any]]:
        meetings = min(last, 3)
        return [
            {
                "fixture": {"id": 900000 + i, "date": f"2024-0{i+1}-15T20:00:00Z"},
                "teams": {
                    "home": {"id": team_a_id if i % 2 == 0 else team_b_id},
                    "away": {"id": team_b_id if i % 2 == 0 else team_a_id},
                },
                "goals": {"home": 1 + i, "away": i},
            }
            for i in range(meetings)
        ]

    def _placeholder_events(self, fixture_id: int) -> list[dict[str, Any]]:
        return [
            {
                "time": {"elapsed": 23},
                "team": {"name": "Home"},
                "player": {"name": "Sample Player"},
                "type": "Goal",
                "detail": "Normal Goal",
            }
        ] if fixture_id % 2 == 0 else []

    def _placeholder_fixture_statistics(self, fixture_id: int) -> list[dict[str, Any]]:
        return [
            {
                "team": {"name": "Home"},
                "statistics": [
                    {"type": "Shots on Goal", "value": 5},
                    {"type": "Ball Possession", "value": "54%"},
                ],
            },
            {
                "team": {"name": "Away"},
                "statistics": [
                    {"type": "Shots on Goal", "value": 3},
                    {"type": "Ball Possession", "value": "46%"},
                ],
            },
        ]

    def _placeholder_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        return [
            {
                "team": {"name": "Home"},
                "formation": "4-3-3",
                "startXI": [{"player": {"name": f"Home Player {i}"}} for i in range(1, 4)],
                "substitutes": [],
            },
            {
                "team": {"name": "Away"},
                "formation": "4-4-2",
                "startXI": [{"player": {"name": f"Away Player {i}"}} for i in range(1, 4)],
                "substitutes": [],
            },
        ]

    def _placeholder_injuries(self, fixture_id: int) -> list[dict[str, Any]]:
        return [
            {
                "team": {"id": 2380, "name": "USA"},
                "player": {"name": "Sample Doubtful", "type": "Missing Fixture", "reason": "Knock"},
            }
        ]

    def _placeholder_odds(self, fixture_id: int) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {"id": fixture_id},
                "bookmakers": [
                    {
                        "name": "Sample Bookmaker",
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.40"},
                                    {"value": "Away", "odd": "3.20"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
