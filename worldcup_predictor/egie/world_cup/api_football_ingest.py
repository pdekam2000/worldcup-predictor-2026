"""API-Football raw ingest for World Cup fixtures → EGIE raw store."""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.config import PROVIDER_API_FOOTBALL
from worldcup_predictor.egie.world_cup.raw_cache import save_raw_with_fallback
from worldcup_predictor.egie.world_cup.config import API_FOOTBALL_LEAGUE_ID, WORLD_CUP_COMPETITION_KEY

logger = logging.getLogger(__name__)

RESOURCE_TYPES = ("events", "lineups", "fixture_statistics", "injuries")


def ingest_api_football_resources(
    fixture_ids: list[int],
    *,
    settings: Settings | None = None,
    max_api_calls: int = 120,
    season: int | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    client = ApiFootballClient(settings)
    api_calls = 0
    saved = 0
    skipped = 0
    errors: list[str] = []

    if not client.is_configured:
        return {"status": "skipped", "reason": "api_not_configured", "saved": 0}

    for fid in fixture_ids:
        row = None
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            repo = FootballIntelligenceRepository(settings.sqlite_path or None)
            row = repo._conn.execute(
                "SELECT season FROM fixtures WHERE fixture_id = ? LIMIT 1",
                (fid,),
            ).fetchone()
        except Exception:
            row = None
        season = int(row[0]) if row and row[0] is not None else None

        for resource in RESOURCE_TYPES:
            if api_calls >= max_api_calls:
                break
            if resource == "injuries":
                method = client.get_injuries
                kwargs = {"fixture_id": fid, "league_id": API_FOOTBALL_LEAGUE_ID, "season": season}
            elif resource == "events":
                method = client.get_fixture_events
                kwargs = {"fixture_id": fid}
            elif resource == "lineups":
                method = client.get_fixture_lineups
                kwargs = {"fixture_id": fid}
            else:
                method = client.get_fixture_statistics
                kwargs = {"fixture_id": fid}
            try:
                result = method(**kwargs)
                api_calls += 1
            except Exception as exc:
                errors.append(f"{fid}:{resource}:{exc}"[:120])
                continue
            if not result or not getattr(result, "ok", False):
                skipped += 1
                continue
            payload = getattr(result, "data", result)
            save_raw_with_fallback(
                settings=settings,
                provider=PROVIDER_API_FOOTBALL,
                resource_type=resource,
                fixture_id=fid,
                payload_json=payload,
                request_endpoint=f"/fixtures/{resource}",
                request_params={"fixture": fid},
                source=getattr(result, "source", "live"),
                competition_key=WORLD_CUP_COMPETITION_KEY,
                season=season,
                league_id=API_FOOTBALL_LEAGUE_ID,
            )
            saved += 1

    return {
        "status": "ok",
        "saved": saved,
        "skipped": skipped,
        "api_calls": api_calls,
        "errors": errors[:20],
    }


def list_wc_fixture_ids(settings: Settings | None = None, *, limit: int = 600) -> list[int]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo._conn.execute(
        """
        SELECT fixture_id FROM fixtures
        WHERE competition_key = ?
        ORDER BY kickoff_utc DESC
        LIMIT ?
        """,
        (WORLD_CUP_COMPETITION_KEY, int(limit)),
    ).fetchall()
    return [int(r[0]) for r in rows]
