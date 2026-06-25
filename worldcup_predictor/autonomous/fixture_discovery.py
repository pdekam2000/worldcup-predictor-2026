"""Discover upcoming fixtures for autonomous prediction — Phase 61."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.competitions import get_competition, list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

FixtureSource = Literal["sqlite_cache", "db_upcoming"]


@dataclass
class DiscoveredFixture:
    fixture_id: int
    competition_key: str
    season: int | None
    league_id: int | None
    home_team: str
    away_team: str
    kickoff_utc: str | None
    status: str
    source: FixtureSource


@dataclass
class FixtureDiscoveryResult:
    fixtures: list[DiscoveredFixture] = field(default_factory=list)
    skipped_recent: int = 0
    skipped_duplicate: int = 0
    competitions_scanned: list[str] = field(default_factory=list)
    api_calls_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixtures": [f.__dict__ for f in self.fixtures],
            "fixture_count": len(self.fixtures),
            "skipped_recent": self.skipped_recent,
            "skipped_duplicate": self.skipped_duplicate,
            "competitions_scanned": self.competitions_scanned,
            "api_calls_used": self.api_calls_used,
        }


def discover_upcoming_fixtures(
    *,
    settings: Settings | None = None,
    competition_keys: list[str] | None = None,
    limit_per_competition: int = 50,
    freshness_hours: int | None = None,
    engines: tuple[str, ...] = ("production", "elite_shadow"),
) -> FixtureDiscoveryResult:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = AutonomousStore(settings)
    freshness = freshness_hours if freshness_hours is not None else settings.autonomous_snapshot_freshness_hours

    keys = competition_keys or list_competition_keys(enabled_only=True)
    result = FixtureDiscoveryResult(competitions_scanned=list(keys))
    seen_ids: set[int] = set()

    for comp_key in keys:
        try:
            comp = get_competition(comp_key)
        except KeyError:
            continue
        if not comp.enabled:
            continue

        rows = repo.list_upcoming_fixtures(comp_key, season=comp.season, limit=limit_per_competition)
        for row in rows:
            fid = int(row["fixture_id"])
            if fid in seen_ids:
                result.skipped_duplicate += 1
                continue
            seen_ids.add(fid)

            if all(store.has_recent_snapshot(fid, eng, freshness_hours=freshness) for eng in engines):
                result.skipped_recent += 1
                continue

            result.fixtures.append(
                DiscoveredFixture(
                    fixture_id=fid,
                    competition_key=comp_key,
                    season=row.get("season") or comp.season,
                    league_id=row.get("league_id") or comp.league_id,
                    home_team=str(row.get("home_team") or ""),
                    away_team=str(row.get("away_team") or ""),
                    kickoff_utc=row.get("kickoff_utc"),
                    status=str(row.get("status") or "NS"),
                    source="db_upcoming",
                )
            )

    return result


def list_completed_fixtures(
    *,
    settings: Settings | None = None,
    competition_keys: list[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    keys = competition_keys or list_competition_keys(enabled_only=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    return repo.list_finished_fixtures_before(
        before_kickoff=now,
        competition_keys=keys,
        limit=limit,
    )
