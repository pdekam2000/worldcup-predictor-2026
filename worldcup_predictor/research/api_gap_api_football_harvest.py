"""PHASE API-GAP-1 — API-Football fallback harvest (cache-first, fill gaps only)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, init_database
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.backfill.api_football_provider_backfill import _RESOURCE_ENDPOINTS
from worldcup_predictor.research.api_gap_staging import ensure_api_gap_tables, log_harvest, upsert_raw_payload

PROVIDER = "api_football"


@dataclass
class ApiFootballHarvestStats:
    fixtures_targeted: int = 0
    cache_rows_imported: int = 0
    api_calls: int = 0
    raw_staged: int = 0
    enrichment_filled: int = 0
    odds_snapshots_created: int = 0
    skipped_existing: int = 0
    skipped_sportmonks_present: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": PROVIDER,
            "fixtures_targeted": self.fixtures_targeted,
            "cache_rows_imported": self.cache_rows_imported,
            "api_calls": self.api_calls,
            "raw_staged": self.raw_staged,
            "enrichment_filled": self.enrichment_filled,
            "odds_snapshots_created": self.odds_snapshots_created,
            "skipped_existing": self.skipped_existing,
            "skipped_sportmonks_present": self.skipped_sportmonks_present,
            "errors": self.errors[:25],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fixture_id_from_params(params_json: str) -> int | None:
    try:
        params = json.loads(params_json)
    except (json.JSONDecodeError, TypeError):
        return None
    for key in ("fixture", "id", "fixture_id"):
        if key in params:
            try:
                return int(params[key])
            except (TypeError, ValueError):
                pass
    return None


def _enrichment_column(data_type: str) -> str | None:
    return {
        "events": "events_json",
        "lineups": "lineups_json",
        "fixture_statistics": "statistics_json",
        "injuries": None,
    }.get(data_type)


def import_api_response_cache(
    repo: FootballIntelligenceRepository,
    *,
    dry_run: bool = False,
    fill_enrichment: bool = True,
) -> ApiFootballHarvestStats:
    conn = repo._conn
    ensure_api_gap_tables(conn)
    stats = ApiFootballHarvestStats()

    endpoint_map = {
        "fixtures/events": "events",
        "fixtures/lineups": "lineups",
        "fixtures/statistics": "fixture_statistics",
        "injuries": "injuries",
        "odds": "odds",
    }

    for row in conn.execute(
        "SELECT cache_key, endpoint, params_json, payload_json FROM api_response_cache"
    ):
        endpoint = str(row["endpoint"] or "")
        data_type = endpoint_map.get(endpoint)
        if not data_type:
            continue
        fid = _fixture_id_from_params(row["params_json"])
        if fid is None:
            continue
        stats.fixtures_targeted += 1

        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        entity = f"af:{fid}"
        if upsert_raw_payload(
            conn,
            provider=PROVIDER,
            entity_key=entity,
            data_type=data_type,
            payload=payload,
            source="api_response_cache",
            fixture_id=fid,
            dry_run=dry_run,
        ):
            stats.raw_staged += 1
            stats.cache_rows_imported += 1
            log_harvest(conn, provider=PROVIDER, data_type=data_type, entity_key=entity, action="imported_cache")

        if data_type == "odds":
            if not conn.execute(
                "SELECT 1 FROM odds_snapshots WHERE fixture_id = ? LIMIT 1", (fid,)
            ).fetchone():
                comp = conn.execute(
                    "SELECT competition_key FROM fixtures WHERE fixture_id = ?", (fid,)
                ).fetchone()
                if comp and not dry_run:
                    repo.save_snapshot(
                        "odds_snapshots",
                        fixture_id=fid,
                        competition_key=str(comp["competition_key"]),
                        payload={
                            "source": "api_gap_cache_import",
                            "api_sports": payload,
                            "snapshot_at": _utc_now(),
                        },
                    )
                    stats.odds_snapshots_created += 1
            else:
                stats.skipped_existing += 1

        col = _enrichment_column(data_type)
        if fill_enrichment and col and not dry_run:
            existing = conn.execute(
                f"SELECT {col} FROM fixture_enrichment WHERE fixture_id = ?", (fid,)
            ).fetchone()
            val = str(existing[0] if existing else "").strip()
            is_empty = existing is None or val in ("", "{}", "[]", "null")
            if is_empty:
                if existing is None:
                    comp = conn.execute(
                        "SELECT competition_key, league_id, season FROM fixtures WHERE fixture_id = ?", (fid,)
                    ).fetchone()
                    if comp:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO fixture_enrichment (fixture_id, competition_key, league_id, season, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (fid, comp["competition_key"], comp["league_id"], comp["season"], _utc_now()),
                        )
                conn.execute(
                    f"UPDATE fixture_enrichment SET {col} = ?, updated_at = ? WHERE fixture_id = ?",
                    (json.dumps(payload, ensure_ascii=False), _utc_now(), fid),
                )
                stats.enrichment_filled += 1

    if not dry_run:
        conn.commit()
    return stats


def harvest_api_football_missing_live(
    repo: FootballIntelligenceRepository,
    client: ApiFootballClient,
    *,
    dry_run: bool = False,
    max_api_calls: int = 30,
) -> ApiFootballHarvestStats:
    conn = repo._conn
    ensure_api_gap_tables(conn)
    stats = ApiFootballHarvestStats()
    if not client.is_configured:
        stats.errors.append("api_football_not_configured")
        return stats

    for row in conn.execute(
        """
        SELECT f.fixture_id, f.competition_key
        FROM fixtures f
        LEFT JOIN fixture_enrichment e ON e.fixture_id = f.fixture_id
        WHERE f.is_placeholder = 0
          AND (
            e.fixture_id IS NULL
            OR e.statistics_json IS NULL
            OR TRIM(e.statistics_json) IN ('', '{}', '[]')
          )
        ORDER BY f.kickoff_utc DESC
        LIMIT 200
        """
    ):
        if stats.api_calls >= max_api_calls:
            break
        fid = int(row["fixture_id"])
        sm = conn.execute(
            "SELECT 1 FROM sportmonks_fixture_enrichment WHERE fixture_id_api_football = ? LIMIT 1",
            (fid,),
        ).fetchone()
        if sm:
            stats.skipped_sportmonks_present += 1
            continue

        for data_type, _endpoint, method_name in _RESOURCE_ENDPOINTS:
            if stats.api_calls >= max_api_calls:
                break
            entity = f"af:{fid}"
            exists = conn.execute(
                "SELECT 1 FROM api_gap_raw_payload WHERE provider=? AND entity_key=? AND data_type=? LIMIT 1",
                (PROVIDER, entity, data_type),
            ).fetchone()
            if exists:
                stats.skipped_existing += 1
                continue
            if dry_run:
                log_harvest(conn, provider=PROVIDER, data_type=data_type, entity_key=entity, action="dry_run_would_fetch")
                continue
            method = getattr(client, method_name)
            result = method(fid)
            stats.api_calls += 1
            if not result.ok or result.data is None:
                stats.errors.append(f"{fid}:{data_type}:{result.error}")
                continue
            if upsert_raw_payload(
                conn,
                provider=PROVIDER,
                entity_key=entity,
                data_type=data_type,
                payload=result.data if isinstance(result.data, (dict, list)) else {"data": result.data},
                source="api_football_live",
                fixture_id=fid,
            ):
                stats.raw_staged += 1
                log_harvest(conn, provider=PROVIDER, data_type=data_type, entity_key=entity, action="fetched")

    if not dry_run:
        conn.commit()
    return stats


def run_api_football_harvest(
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
    max_api_calls: int = 30,
    use_live_api: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path)
    cache_stats = import_api_response_cache(repo, dry_run=dry_run)
    live_stats = ApiFootballHarvestStats()
    if use_live_api:
        client = ApiFootballClient(settings, cache=ApiCache(Path(settings.api_cache_dir)))
        live_stats = harvest_api_football_missing_live(
            repo, client, dry_run=dry_run, max_api_calls=max_api_calls
        )
    shots_after = repo._conn.execute(
        "SELECT COUNT(1) FROM api_gap_raw_payload WHERE provider=? AND data_type='fixture_statistics'",
        (PROVIDER,),
    ).fetchone()[0]
    repo.close()
    return {
        "cache_import": cache_stats.to_dict(),
        "live_fetch": live_stats.to_dict(),
        "statistics_staged_after": shots_after,
    }
