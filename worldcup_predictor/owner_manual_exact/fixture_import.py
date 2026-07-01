"""Import knockout fixtures for manual owner match list from API-Football."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.european_fixture_feed import (
    _store_raw_payload,
    _upsert_feed_row,
    ensure_euro_fixture_feed_tables,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.sqlite_retry import run_with_sqlite_retry
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR
from worldcup_predictor.owner_manual_exact.team_aliases import (
    fixture_pair_key,
    load_alias_config,
    normalize_for_match,
)

PHASE = "OWNER-MANUAL-KNOCKOUT-IMPORT"
DEFAULT_FROM = "2026-07-01"
DEFAULT_TO = "2026-07-05"


@dataclass
class KnockoutImportResult:
    phase: str = PHASE
    from_date: str = DEFAULT_FROM
    to_date: str = DEFAULT_TO
    inserted: int = 0
    updated: int = 0
    skipped_existing: int = 0
    skipped_duplicate: int = 0
    api_fetched: int = 0
    errors: list[str] = field(default_factory=list)
    fixtures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped_existing": self.skipped_existing,
            "skipped_duplicate": self.skipped_duplicate,
            "api_fetched": self.api_fetched,
            "errors": self.errors,
            "fixtures": self.fixtures,
        }


def _fixture_row(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key
        FROM fixtures WHERE fixture_id = ? LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def _import_item(
    item: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    competition_key: str,
    league_id: int,
    season: int,
    dry_run: bool,
) -> str:
    parsed = parse_api_fixture_item(item, source="live")
    if parsed is None:
        return "parse_failed"
    fid = int(parsed.fixture_id)
    existing = _fixture_row(conn, fid)
    if existing and not dry_run:
        repo.upsert_fixture(
            parsed,
            competition_key=competition_key,
            league_id=league_id,
            season=season,
        )
        return "updated"

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
    return "inserted" if not existing else "updated"


def import_knockout_fixtures(
    *,
    from_date: str = DEFAULT_FROM,
    to_date: str = DEFAULT_TO,
    settings: Settings | None = None,
    dry_run: bool = False,
    force_ids: list[int] | None = None,
) -> KnockoutImportResult:
    settings = settings or get_settings()
    result = KnockoutImportResult(from_date=from_date, to_date=to_date)
    comp = get_competition("world_cup_2026")
    api = ApiFootballClient(settings)
    cfg = load_alias_config()
    known_ids = list(force_ids or [])
    if not known_ids:
        known_ids = list({int(v) for v in (cfg.get("known_knockout_fixture_ids") or {}).values()})

    def _run() -> None:
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        conn = repo._conn
        seen_ids: set[int] = set()
        try:
            if api.is_configured:
                fetch = api.get_historical_fixtures(
                    league_id=comp.league_id,
                    season=comp.season,
                    from_date=from_date,
                    to_date=to_date,
                )
                if fetch.ok and isinstance(fetch.data, list):
                    result.api_fetched = len(fetch.data)
                    for item in fetch.data:
                        fid = int((item.get("fixture") or {}).get("id") or 0)
                        if fid <= 0 or fid in seen_ids:
                            if fid in seen_ids:
                                result.skipped_duplicate += 1
                            continue
                        seen_ids.add(fid)
                        existed = _fixture_row(conn, fid) is not None
                        outcome = _import_item(
                            item,
                            conn=conn,
                            repo=repo,
                            competition_key="world_cup_2026",
                            league_id=comp.league_id,
                            season=comp.season,
                            dry_run=dry_run,
                        )
                        if outcome == "inserted":
                            result.inserted += 1
                        elif outcome == "updated":
                            result.updated += 1
                        elif existed:
                            result.skipped_existing += 1
                        row = _fixture_row(conn, fid)
                        if row:
                            result.fixtures.append(row)
                else:
                    result.errors.append(fetch.error or "API fixture range fetch failed")
            else:
                result.errors.append("API_FOOTBALL_KEY not configured")

            for fid in known_ids:
                if fid in seen_ids:
                    continue
                if _fixture_row(conn, fid) and not dry_run:
                    result.skipped_existing += 1
                    row = _fixture_row(conn, fid)
                    if row:
                        result.fixtures.append(row)
                    continue
                if not api.is_configured:
                    continue
                fetch = api.get_fixture_by_id(fid)
                if not fetch.ok or not isinstance(fetch.data, list) or not fetch.data:
                    result.errors.append(fetch.error or f"{fid}: fetch failed")
                    continue
                outcome = _import_item(
                    fetch.data[0],
                    conn=conn,
                    repo=repo,
                    competition_key="world_cup_2026",
                    league_id=comp.league_id,
                    season=comp.season,
                    dry_run=dry_run,
                )
                if outcome == "inserted":
                    result.inserted += 1
                elif outcome == "updated":
                    result.updated += 1
                row = _fixture_row(conn, fid)
                if row:
                    result.fixtures.append(row)
            if not dry_run:
                conn.commit()
        finally:
            repo.close()

    run_with_sqlite_retry(_run)
    return result


def save_import_audit(result: KnockoutImportResult, *, process_date: date) -> Path:
    path = ARTIFACTS_DIR / f"manual_knockout_fixture_import_{process_date.isoformat().replace('-', '')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
