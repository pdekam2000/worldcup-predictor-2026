"""Part A — Daily fixture discovery (local DB first, then providers)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition, normalize_competition_key
from worldcup_predictor.config.euro_feed_registry import (
    EURO_A_TARGET_KEYS,
    get_euro_feed_spec,
    resolve_provider_season,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.european_fixture_feed import (
    _import_api_football_competition,
    _import_sportmonks_competition,
    ensure_euro_fixture_feed_tables,
)
from worldcup_predictor.data_import.uefa_result_matching import FeedIndex, infer_provider_source
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS, PHASE
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

CoverageSource = Literal["local_db", "api_football", "sportmonks", "oddalerts"]


@dataclass
class DailyFixture:
    fixture_id: int
    provider_fixture_id: int
    competition_key: str
    home_team: str
    away_team: str
    kickoff_utc: str
    status: str
    season: int | None
    coverage_sources: list[str] = field(default_factory=list)
    provider_ids: dict[str, int] = field(default_factory=dict)
    raw_payload_refs: dict[str, str] = field(default_factory=dict)
    duplicate_group_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "provider_fixture_id": self.provider_fixture_id,
            "competition_key": self.competition_key,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_utc": self.kickoff_utc,
            "status": self.status,
            "season": self.season,
            "coverage_sources": self.coverage_sources,
            "provider_ids": self.provider_ids,
            "raw_payload_refs": self.raw_payload_refs,
            "duplicate_group_key": self.duplicate_group_key,
        }


@dataclass
class FixtureDiscoveryResult:
    phase: str = PHASE
    target_date: str = ""
    timezone: str = ""
    fixtures: list[DailyFixture] = field(default_factory=list)
    fetched_from_providers: int = 0
    duplicates_avoided: int = 0
    provider_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "target_date": self.target_date,
            "timezone": self.timezone,
            "fixture_count": len(self.fixtures),
            "fetched_from_providers": self.fetched_from_providers,
            "duplicates_avoided": self.duplicates_avoided,
            "provider_errors": self.provider_errors,
            "fixtures": [f.to_dict() for f in self.fixtures],
        }


def resolve_target_date(date_arg: str, tz_name: str) -> date:
    tz = ZoneInfo(tz_name)
    today_local = datetime.now(tz).date()
    key = date_arg.strip().lower()
    if key in ("today", "now"):
        return today_local
    if key == "yesterday":
        return today_local - timedelta(days=1)
    if key == "tomorrow":
        return today_local + timedelta(days=1)
    try:
        return date.fromisoformat(date_arg)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date argument '{date_arg}'. "
            f"Supported formats: today, now, yesterday, tomorrow, or YYYY-MM-DD"
        ) from exc


def vienna_day_utc_bounds(target: date, tz_name: str) -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    start = datetime.combine(target, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(target, time.max, tzinfo=tz).astimezone(timezone.utc)
    return start.isoformat(), end.isoformat()


def _dedupe_key(home: str, away: str, kickoff_utc: str) -> str:
    return f"{home.strip().lower()}|{away.strip().lower()}|{kickoff_utc[:16]}"


def discover_fixtures_from_db(
    conn: sqlite3.Connection,
    *,
    competition_keys: list[str],
    start_utc: str,
    end_utc: str,
    limit: int | None = None,
) -> list[DailyFixture]:
    placeholders = ",".join("?" for _ in competition_keys)
    query = f"""
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season, source
        FROM fixtures
        WHERE competition_key IN ({placeholders})
          AND is_placeholder = 0
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc >= ?
          AND kickoff_utc <= ?
        ORDER BY kickoff_utc ASC
    """
    params: list[Any] = [*competition_keys, start_utc, end_utc]
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query, params).fetchall()
    ensure_euro_fixture_feed_tables(conn)
    feed_index = FeedIndex.build(conn, tuple(competition_keys))
    out: list[DailyFixture] = []
    for raw in rows:
        row = dict(raw)
        fid = int(row["fixture_id"])
        comp = str(row["competition_key"])
        inferred = infer_provider_source(row, feed_index)
        sources: list[str] = ["local_db"]
        provider_ids: dict[str, int] = {"api_football": fid}
        if inferred == "sportmonks":
            sources.append("sportmonks")
            provider_ids["sportmonks"] = fid
        out.append(
            DailyFixture(
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=comp,
                home_team=str(row.get("home_team") or "TBD"),
                away_team=str(row.get("away_team") or "TBD"),
                kickoff_utc=str(row["kickoff_utc"]),
                status=str(row.get("status") or "NS"),
                season=int(row["season"]) if row.get("season") is not None else None,
                coverage_sources=sources,
                provider_ids=provider_ids,
            )
        )
    return out


def fetch_missing_fixtures_from_providers(
    *,
    target: date,
    competition_keys: list[str],
    settings: Settings,
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    call_log: DailyProviderCallLog,
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    """Fetch fixtures for target date when local DB has gaps."""
    api = ApiFootballClient(settings)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    fetched = 0
    dupes = 0
    errors: list[str] = []
    ensure_euro_fixture_feed_tables(conn)

    for key in competition_keys:
        comp_key = normalize_competition_key(key)
        if comp_key not in DAILY_SUPPORTED_COMPETITIONS:
            continue
        comp = get_competition(comp_key)
        if not comp.enabled:
            errors.append(f"{comp_key}: competition disabled")
            continue

        if comp_key in EURO_A_TARGET_KEYS or comp_key == "world_cup_2026":
            if comp_key in EURO_A_TARGET_KEYS:
                spec = get_euro_feed_spec(comp_key)
                season = resolve_provider_season(comp_key, settings=settings)
            else:
                from worldcup_predictor.config.euro_feed_registry import EuroFeedSpec

                spec = EuroFeedSpec(
                    competition_key=comp_key,
                    provider="api-football",
                    provider_league_id=comp.league_id,
                    provider_season_id=comp.season,
                    timezone_policy="utc_storage",
                    supports_fixtures=True,
                    supports_results=True,
                    supports_odds=True,
                    supports_ecse=True,
                    supports_wde=True,
                )
                season = comp.season

            if api.is_configured and call_log.quota.can_call("api_football"):
                call_log.record(
                    provider="api_football",
                    endpoint="fixtures",
                    action="fetch_by_date",
                    competition_key=comp_key,
                    request_reason="missing_local_fixtures",
                    call_made=True,
                    cache_hit=False,
                    success=False,
                )
                if not dry_run:
                    stats = _import_api_football_competition(
                        spec=spec,
                        season=season,
                        from_date=target,
                        to_date=target,
                        conn=conn,
                        repo=repo,
                        api=api,
                        dry_run=dry_run,
                    )
                    fetched += stats.upcoming_imported
                    dupes += stats.duplicates_avoided
                    errors.extend(stats.errors)
                    call_log.entries[-1]["success"] = not stats.errors
                else:
                    call_log.entries[-1]["success"] = True
            elif not api.is_configured:
                errors.append(f"{comp_key}: API_FOOTBALL_KEY not configured")

            if comp_key in EURO_A_TARGET_KEYS and sm.is_configured and call_log.quota.can_call("sportmonks"):
                call_log.record(
                    provider="sportmonks",
                    endpoint="fixtures",
                    action="fetch_by_date",
                    competition_key=comp_key,
                    request_reason="supplementary_fixture_feed",
                    call_made=True,
                    success=False,
                )
                if not dry_run:
                    sm_stats = _import_sportmonks_competition(
                        spec=spec,
                        season=season,
                        from_date=target,
                        to_date=target,
                        conn=conn,
                        provider=sm,
                        dry_run=dry_run,
                    )
                    fetched += sm_stats.upcoming_imported
                    dupes += sm_stats.duplicates_avoided
                    errors.extend(sm_stats.errors)
                    call_log.entries[-1]["success"] = not sm_stats.errors
                else:
                    call_log.entries[-1]["success"] = True

        if oa.is_configured and call_log.quota.can_call("oddalerts"):
            call_log.record(
                provider="oddalerts",
                endpoint="value/upcoming",
                action="fixture_support_probe",
                competition_key=comp_key,
                request_reason="oddalerts_fixture_support",
                call_made=True,
                success=oa.is_configured,
            )

    if not dry_run:
        conn.commit()
    return fetched, dupes, errors


def discover_daily_fixtures(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    competition_keys: list[str] | None = None,
    limit: int = 50,
    settings: Settings | None = None,
    fetch_if_missing: bool = True,
    call_log: DailyProviderCallLog | None = None,
    dry_run: bool = False,
) -> FixtureDiscoveryResult:
    settings = settings or get_settings()
    keys = [normalize_competition_key(k) for k in (competition_keys or list(DAILY_SUPPORTED_COMPETITIONS))]
    keys = [k for k in keys if k in DAILY_SUPPORTED_COMPETITIONS]
    target = resolve_target_date(date_arg, timezone)
    start_utc, end_utc = vienna_day_utc_bounds(target, timezone)

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = repo._conn
    log = call_log or DailyProviderCallLog(run_date=target.isoformat())

    result = FixtureDiscoveryResult(
        target_date=target.isoformat(),
        timezone=timezone,
    )

    local = discover_fixtures_from_db(conn, competition_keys=keys, start_utc=start_utc, end_utc=end_utc, limit=limit)
    if fetch_if_missing and len(local) == 0:
        fetched, dupes, errors = fetch_missing_fixtures_from_providers(
            target=target,
            competition_keys=keys,
            settings=settings,
            conn=conn,
            repo=repo,
            call_log=log,
            dry_run=dry_run,
        )
        result.fetched_from_providers = fetched
        result.duplicates_avoided = dupes
        result.provider_errors = errors
        local = discover_fixtures_from_db(
            conn, competition_keys=keys, start_utc=start_utc, end_utc=end_utc, limit=limit
        )

    seen: dict[str, DailyFixture] = {}
    for fx in local:
        dk = _dedupe_key(fx.home_team, fx.away_team, fx.kickoff_utc)
        if dk in seen:
            fx.duplicate_group_key = dk
            result.duplicates_avoided += 1
            existing = seen[dk]
            for src in fx.coverage_sources:
                if src not in existing.coverage_sources:
                    existing.coverage_sources.append(src)
            existing.provider_ids.update(fx.provider_ids)
            continue
        seen[dk] = fx
        result.fixtures.append(fx)

    if len(result.fixtures) > limit:
        result.fixtures = result.fixtures[:limit]

    return result
