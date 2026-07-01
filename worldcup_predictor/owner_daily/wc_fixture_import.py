"""WC-DAILY-WDE-INPUTS — Import World Cup fixtures with SQLite lock retry."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.euro_feed_registry import EuroFeedSpec
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.european_fixture_feed import (
    _import_api_football_competition,
    _store_raw_payload,
    _upsert_feed_row,
    ensure_euro_fixture_feed_tables,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.sqlite_retry import run_with_sqlite_retry
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog

PHASE = "WC-DAILY-WDE-INPUTS"

WC_TODAY_FIXTURE_IDS: tuple[int, ...] = (
    1564789,  # Ivory Coast vs Norway
    1565177,  # France vs Sweden
    1567306,  # Mexico vs Ecuador
    1562345,  # Netherlands vs Morocco
)


@dataclass
class WcFixtureImportResult:
    phase: str = PHASE
    target_date: str = ""
    imported_by_date: int = 0
    imported_by_id: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)
    fixtures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "target_date": self.target_date,
            "imported_by_date": self.imported_by_date,
            "imported_by_id": self.imported_by_id,
            "skipped_existing": self.skipped_existing,
            "errors": self.errors,
            "fixtures": self.fixtures,
        }


def _fixture_exists(conn: sqlite3.Connection, fixture_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM fixtures WHERE fixture_id = ? AND is_placeholder = 0 LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return row is not None


def _import_single_fixture(
    item: dict[str, Any],
    *,
    competition_key: str,
    season: int,
    league_id: int,
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    dry_run: bool,
) -> str:
    parsed = parse_api_fixture_item(item, source="live")
    if parsed is None:
        return "parse_failed"
    fid = int(parsed.fixture_id)
    if _fixture_exists(conn, fid):
        return "existing"

    ensure_euro_fixture_feed_tables(conn)
    entity_key = f"fixtures:{fid}"
    raw_ref = _store_raw_payload(
        conn,
        provider="api-football",
        entity_key=entity_key,
        payload=item,
        dry_run=dry_run,
    )
    kickoff = parsed.kickoff_time.isoformat() if parsed.kickoff_time else ""
    _upsert_feed_row(
        conn,
        fixture_id=fid,
        provider="api-football",
        provider_fixture_id=fid,
        competition_key=competition_key,
        home_team=parsed.home_team,
        away_team=parsed.away_team,
        kickoff_utc=kickoff,
        status=parsed.status,
        season=season,
        raw_payload_ref=raw_ref,
        dry_run=dry_run,
    )
    if not dry_run:
        repo.upsert_fixture(
            parsed,
            competition_key=competition_key,
            league_id=league_id,
            season=season,
        )
    return "imported"


def import_wc_fixtures_for_date(
    target: date,
    *,
    settings: Settings | None = None,
    call_log: DailyProviderCallLog | None = None,
    dry_run: bool = False,
    force_refresh: bool = False,
) -> WcFixtureImportResult:
    settings = settings or get_settings()
    result = WcFixtureImportResult(target_date=target.isoformat())
    comp = get_competition("world_cup_2026")
    spec = EuroFeedSpec(
        competition_key="world_cup_2026",
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
    api = ApiFootballClient(settings)

    def _run_import() -> None:
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        conn = repo._conn
        try:
            if api.is_configured:
                stats = _import_api_football_competition(
                    spec=spec,
                    season=comp.season,
                    from_date=target,
                    to_date=target,
                    conn=conn,
                    repo=repo,
                    api=api,
                    dry_run=dry_run,
                )
                result.imported_by_date = stats.upcoming_imported + stats.fixtures_synced
                result.errors.extend(stats.errors)

            for fid in WC_TODAY_FIXTURE_IDS:
                if not force_refresh and _fixture_exists(conn, fid):
                    result.skipped_existing += 1
                    row = conn.execute(
                        "SELECT fixture_id, home_team, away_team, kickoff_utc, status FROM fixtures WHERE fixture_id=?",
                        (fid,),
                    ).fetchone()
                    if row:
                        result.fixtures.append(dict(row))
                    continue
                if not api.is_configured:
                    result.errors.append(f"{fid}: API_FOOTBALL_KEY not configured")
                    continue
                if call_log:
                    call_log.record(
                        provider="api_football",
                        endpoint="fixtures",
                        action="import_by_id",
                        fixture_id=fid,
                        competition_key="world_cup_2026",
                        request_reason="wc_fixture_hotfix",
                        call_made=True,
                        cache_hit=False,
                        success=False,
                    )
                fetch = api.get_fixture_by_id(fid)
                if call_log and call_log.entries:
                    call_log.entries[-1]["success"] = fetch.ok
                if not fetch.ok or not isinstance(fetch.data, list) or not fetch.data:
                    result.errors.append(fetch.error or f"{fid}: fixture fetch failed")
                    continue
                outcome = _import_single_fixture(
                    fetch.data[0],
                    competition_key="world_cup_2026",
                    season=comp.season,
                    league_id=comp.league_id,
                    conn=conn,
                    repo=repo,
                    dry_run=dry_run,
                )
                if outcome == "imported":
                    result.imported_by_id += 1
                elif outcome == "existing":
                    result.skipped_existing += 1
                row = conn.execute(
                    "SELECT fixture_id, home_team, away_team, kickoff_utc, status FROM fixtures WHERE fixture_id=?",
                    (fid,),
                ).fetchone()
                if row:
                    result.fixtures.append(dict(row))
            if not dry_run:
                conn.commit()
        finally:
            repo.close()

    run_with_sqlite_retry(_run_import)
    return result
