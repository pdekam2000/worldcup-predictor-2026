"""Sportmonks provider backfill into EGIE PostgreSQL + SQLite xg_snapshots."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.competitions import PREMIER_LEAGUE
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.backfill.sportmonks_pl_lookup import lookup_premier_league_fixture
from worldcup_predictor.egie.config import PROVIDER_SPORTMONKS
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.providers.sportmonks_xg_extraction import (
    extract_fixture_xg_match,
    parse_sportmonks_xg_match,
)

logger = logging.getLogger(__name__)

_FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")


def _pl_fixture_targets(
    repo: FootballIntelligenceRepository,
    *,
    fixture_ids: list[int] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    ph = ",".join("?" * len(_FINISHED))
    q = f"""
        SELECT fixture_id, home_team, away_team, kickoff_utc
        FROM fixtures
        WHERE competition_key = 'premier_league' AND is_placeholder = 0
          AND status IN ({ph})
        ORDER BY kickoff_utc ASC
    """
    params: list[Any] = list(_FINISHED)
    if fixture_ids:
        ids_ph = ",".join("?" * len(fixture_ids))
        q = q.replace("ORDER BY", f"AND fixture_id IN ({ids_ph}) ORDER BY")
        params.extend(fixture_ids)
    if limit:
        q += " LIMIT ?"
        params.append(int(limit))
    return [dict(r) for r in repo._conn.execute(q, params).fetchall()]


def _has_egie_xg(store: EgieRawStoreRepository, fixture_id: int) -> bool:
    return bool(
        store.get_latest_raw(
            provider=PROVIDER_SPORTMONKS,
            resource_type="xg",
            fixture_id=fixture_id,
        )
    )


def _save_xg_to_sqlite(
    repo: FootballIntelligenceRepository,
    *,
    fixture_id: int,
    parsed: dict[str, Any],
    raw_fixture: dict[str, Any],
) -> None:
    payload = {
        "fixture_id": fixture_id,
        "source": "sportmonks_xg_backfill",
        "home_xg": parsed.get("home_xg"),
        "away_xg": parsed.get("away_xg"),
        "raw_fixture": raw_fixture,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    }
    repo.save_snapshot("xg_snapshots", fixture_id=fixture_id, competition_key="premier_league", payload=payload)


def run_sportmonks_pl_backfill(
    *,
    fixture_ids: list[int] | None = None,
    limit_fixtures: int | None = None,
    max_api_calls: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = EgieRawStoreRepository(settings)
    targets = _pl_fixture_targets(repo, fixture_ids=fixture_ids, limit=limit_fixtures)

    api_calls = 0
    mapped = 0
    xg_saved = 0
    skipped_existing = 0
    skipped_cap = 0
    errors: list[str] = []

    for row in targets:
        fid = int(row["fixture_id"])
        if _has_egie_xg(store, fid) and repo.has_xg_snapshot(fid):
            skipped_existing += 1
            continue
        if api_calls >= max_api_calls:
            skipped_cap += 1
            continue

        sm_row = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(fid)
        sm_id = int(sm_row["sportmonks_fixture_id"]) if sm_row and sm_row.get("sportmonks_fixture_id") else None
        lookup_calls = 0

        if not sm_id:
            if api_calls >= max_api_calls:
                skipped_cap += 1
                continue
            sm_id, lookup_src, lookup_calls = lookup_premier_league_fixture(
                api_fixture_id=fid,
                home_team=str(row.get("home_team") or ""),
                away_team=str(row.get("away_team") or ""),
                kickoff_date=str(row.get("kickoff_utc") or ""),
                settings=settings,
            )
            api_calls += lookup_calls
            if sm_id:
                mapped += 1

        if not sm_id:
            continue

        extraction = extract_fixture_xg_match(
            api_fixture_id=fid,
            sportmonks_fixture_id=sm_id,
            home_team=str(row.get("home_team") or ""),
            away_team=str(row.get("away_team") or ""),
            kickoff_date=str(row.get("kickoff_utc") or ""),
            settings=settings,
            repo=repo,
            allow_non_wc=True,
        )
        api_calls += int(extraction.api_calls_made or 0)

        if extraction.raw_available and extraction.parsed:
            parsed = extraction.parsed if isinstance(extraction.parsed, dict) else {}
            envelope = {
                "endpoint": extraction.endpoint_path,
                "includes": list(extraction.includes),
                "parsed": {
                    "home_xg": parsed.get("home_xg"),
                    "away_xg": parsed.get("away_xg"),
                },
                "source_chain": list(extraction.source_chain),
            }
            save = store.save_raw_response(
                provider=PROVIDER_SPORTMONKS,
                resource_type="xg",
                request_endpoint=extraction.endpoint_path,
                request_params={"sportmonks_fixture_id": sm_id, "api_fixture_id": fid},
                payload_json=envelope,
                source="sportmonks_backfill",
                competition_key=PREMIER_LEAGUE.key,
                league_id=PREMIER_LEAGUE.league_id,
                season=PREMIER_LEAGUE.season,
                fixture_id=fid,
                sportmonks_fixture_id=sm_id,
            )
            if save.saved or save.skipped_duplicate:
                xg_saved += 1
                raw: dict[str, Any] | None = None
                if sm_row and sm_row.get("raw_json"):
                    try:
                        raw = json.loads(sm_row["raw_json"])
                    except json.JSONDecodeError:
                        raw = None
                if raw is None:
                    cached = repo.get_sportmonks_fixture_enrichment_cache(sm_id) if sm_id else None
                    if cached and cached.get("raw_json"):
                        try:
                            raw = json.loads(cached["raw_json"])
                        except json.JSONDecodeError:
                            raw = {"parsed": parsed}
                    else:
                        raw = {"parsed": parsed}
                _save_xg_to_sqlite(repo, fixture_id=fid, parsed=parsed, raw_fixture=raw)
        elif extraction.message:
            errors.append(f"{fid}:{extraction.message[:120]}")

    return {
        "provider": PROVIDER_SPORTMONKS,
        "targets": len(targets),
        "sportmonks_newly_mapped": mapped,
        "xg_rows_saved": xg_saved,
        "skipped_existing": skipped_existing,
        "skipped_api_cap": skipped_cap,
        "api_calls_live": api_calls,
        "errors_sample": errors[:15],
    }
