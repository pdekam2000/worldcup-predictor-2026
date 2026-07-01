"""PHASE ECSE-LIVE-1 — Resolve fixtures across API-Football, Sportmonks, OddAlerts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.providers.oddalerts_historical_odds import OddAlertsHistoricalOddsIngester
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_fixture_lookup import (
    lookup_world_cup_fixture,
    team_names_match,
)
from worldcup_predictor.research.ecse_live.api_log import ApiCallTracker
from worldcup_predictor.research.ecse_live.smoke_targets import TEAM_ALIASES

PHASE = "ECSE-LIVE-1"


@dataclass
class ResolvedFixture:
    home_team: str
    away_team: str
    fixture_id: int | None = None
    kickoff_utc: str | None = None
    competition_key: str = "world_cup_2026"
    sportmonks_fixture_id: int | None = None
    oddalerts_fixture_id: int | None = None
    registry_fixture_id: int | None = None
    resolve_sources: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_team": self.home_team,
            "away_team": self.away_team,
            "fixture_id": self.fixture_id,
            "kickoff_utc": self.kickoff_utc,
            "competition_key": self.competition_key,
            "sportmonks_fixture_id": self.sportmonks_fixture_id,
            "oddalerts_fixture_id": self.oddalerts_fixture_id,
            "registry_fixture_id": self.registry_fixture_id,
            "resolve_sources": self.resolve_sources,
        }


def _teams_match(expected_home: str, expected_away: str, home: str, away: str) -> bool:
    if team_names_match(expected_home, home) and team_names_match(expected_away, away):
        return True
    eh = expected_home.lower().strip()
    ea = expected_away.lower().strip()
    for alias in TEAM_ALIASES.get(eh, ()):
        if team_names_match(alias, home) and team_names_match(ea, away):
            return True
    for alias in TEAM_ALIASES.get(ea, ()):
        if team_names_match(eh, home) and team_names_match(alias, away):
            return True
    return False


def _kickoff_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def resolve_api_football_fixture(
    *,
    home_team: str,
    away_team: str,
    settings: Settings | None = None,
    tracker: ApiCallTracker | None = None,
    conn=None,
) -> ResolvedFixture | None:
    settings = settings or get_settings()
    client = ApiFootballClient(settings)
    comp = get_competition("world_cup_2026")
    result = ResolvedFixture(home_team=home_team, away_team=away_team)

    if not client.is_configured:
        tracker and tracker.record(
            conn, provider="api_football", endpoint="fixtures", entity_key=f"{home_team}|{away_team}",
            action="discover", status="not_configured",
        )
        return None

    res = client.get_historical_fixtures(
        league_id=comp.league_id,
        season=comp.season,
        from_date="2026-06-01",
        to_date="2026-07-15",
    )
    tracker and tracker.record(
        conn,
        provider="api_football",
        endpoint="fixtures",
        entity_key=f"{home_team}|{away_team}",
        action="discover",
        status="ok" if res.ok else "error",
        details={"count": len(res.data or []), "error": res.error},
    )
    if not res.ok or not res.data:
        return None

    for item in res.data:
        teams = item.get("teams") or {}
        h = str(teams.get("home", {}).get("name") or "")
        a = str(teams.get("away", {}).get("name") or "")
        if not _teams_match(home_team, away_team, h, a):
            continue
        fixture = item.get("fixture") or {}
        fid = int(fixture.get("id") or 0)
        if not fid:
            continue
        result.fixture_id = fid
        result.kickoff_utc = _kickoff_iso(fixture.get("date"))
        result.resolve_sources["api_football"] = {"fixture_id": fid, "home": h, "away": a}
        return result
    return None


def resolve_sportmonks_fixture(
    resolved: ResolvedFixture,
    *,
    settings: Settings | None = None,
    tracker: ApiCallTracker | None = None,
    conn=None,
) -> None:
    settings = settings or get_settings()
    kickoff_date = (resolved.kickoff_utc or "")[:10] or None
    lookup = lookup_world_cup_fixture(
        api_fixture_id=int(resolved.fixture_id or 0),
        home_team=resolved.home_team,
        away_team=resolved.away_team,
        kickoff_date=kickoff_date,
        settings=settings,
    )
    tracker and tracker.record(
        conn,
        provider="sportmonks",
        endpoint=lookup.endpoint,
        entity_key=str(resolved.fixture_id or resolved.home_team),
        action="lookup",
        status="found" if lookup.found else "not_found",
        details={"reason": lookup.reason, "from_cache": lookup.from_cache},
    )
    if lookup.found and lookup.sportmonks_fixture_id:
        resolved.sportmonks_fixture_id = int(lookup.sportmonks_fixture_id)
        resolved.resolve_sources["sportmonks"] = {
            "fixture_id": resolved.sportmonks_fixture_id,
            "reason": lookup.reason,
        }


def _match_oddalerts_row(home_team: str, away_team: str, row: dict[str, Any]) -> bool:
    h = str(row.get("home_name") or row.get("home") or "")
    a = str(row.get("away_name") or row.get("away") or "")
    return _teams_match(home_team, away_team, h, a)


def resolve_oddalerts_fixture(
    resolved: ResolvedFixture,
    *,
    settings: Settings | None = None,
    tracker: ApiCallTracker | None = None,
    conn=None,
    season: int = 2026,
) -> None:
    settings = settings or get_settings()
    client = OddAlertsClient()
    if not client.is_configured:
        tracker and tracker.record(
            conn, provider="oddalerts", endpoint="value/upcoming",
            entity_key=f"{resolved.home_team}|{resolved.away_team}",
            action="discover", status="not_configured",
        )
        return

    ingester = OddAlertsHistoricalOddsIngester(settings=settings)
    from worldcup_predictor.providers.oddalerts_historical_odds import IngestStats

    stats = IngestStats(league="world_cup", season=season)
    discovered = ingester.discover_fixtures(
        league="world_cup", season=season, stats=stats, max_discovery_pages=5,
    )
    tracker and tracker.record(
        conn,
        provider="oddalerts",
        endpoint="value/upcoming+value/results",
        entity_key=f"{resolved.home_team}|{resolved.away_team}",
        action="discover",
        status="ok",
        details={"pool_size": len(discovered), "api_calls": stats.api_calls_used},
    )

    for d in discovered:
        if _teams_match(resolved.home_team, resolved.away_team, d.home_team, d.away_team):
            resolved.oddalerts_fixture_id = int(d.oddalerts_fixture_id)
            resolved.resolve_sources["oddalerts"] = {
                "fixture_id": d.oddalerts_fixture_id,
                "source": d.source,
                "home": d.home_team,
                "away": d.away_team,
            }
            return

    # Direct upcoming scan fallback
    upcoming = client.get_value_upcoming(per_page=250)
    tracker and tracker.record(
        conn,
        provider="oddalerts",
        endpoint="value/upcoming",
        entity_key=f"{resolved.home_team}|{resolved.away_team}",
        action="discover_fallback",
        status="ok" if upcoming.data else "error",
        details={"error": upcoming.error},
    )
    for row in (upcoming.data or {}).get("data") or []:
        if _match_oddalerts_row(resolved.home_team, resolved.away_team, row):
            fid = int(row.get("id") or 0)
            if fid:
                resolved.oddalerts_fixture_id = fid
                resolved.resolve_sources["oddalerts"] = {"fixture_id": fid, "source": "value/upcoming_direct"}
                return


def resolve_registry_mapping(
    resolved: ResolvedFixture,
    conn,
) -> None:
    if resolved.fixture_id is None:
        return
    from worldcup_predictor.research.ecse_match_display import resolve_registry_fixture_id

    reg = resolve_registry_fixture_id(conn, int(resolved.fixture_id))
    rid = reg.get("registry_fixture_id")
    if rid:
        resolved.registry_fixture_id = int(rid)
        resolved.resolve_sources["registry"] = reg


def resolve_fixture_all_providers(
    *,
    home_team: str,
    away_team: str,
    settings: Settings | None = None,
    tracker: ApiCallTracker | None = None,
    conn=None,
) -> ResolvedFixture | None:
    settings = settings or get_settings()
    tracker = tracker or ApiCallTracker()
    base = resolve_api_football_fixture(
        home_team=home_team,
        away_team=away_team,
        settings=settings,
        tracker=tracker,
        conn=conn,
    )
    if base is None:
        return None
    resolve_sportmonks_fixture(base, settings=settings, tracker=tracker, conn=conn)
    resolve_oddalerts_fixture(base, settings=settings, tracker=tracker, conn=conn)
    if conn is not None:
        resolve_registry_mapping(base, conn)
    return base
