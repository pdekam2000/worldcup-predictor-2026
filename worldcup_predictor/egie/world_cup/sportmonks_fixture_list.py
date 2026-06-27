"""Resolve Sportmonks fixture rows for World Cup bulk import."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.config import SPORTMONKS_LEAGUE_ID, WORLD_CUP_COMPETITION_KEY


def list_sportmonks_wc_fixtures(
    settings: Settings | None = None,
    *,
    limit: int = 600,
) -> list[dict[str, Any]]:
    """Map API-Football fixtures to Sportmonks IDs when enrichment cache exists."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo._conn.execute(
        """
        SELECT f.fixture_id, f.season, e.sportmonks_fixture_id
        FROM fixtures f
        LEFT JOIN sportmonks_fixture_enrichment e
          ON e.fixture_id_api_football = f.fixture_id AND e.status = 'ok'
        WHERE f.competition_key = ?
        ORDER BY f.kickoff_utc DESC
        LIMIT ?
        """,
        (WORLD_CUP_COMPETITION_KEY, int(limit)),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        af_id = int(r[0])
        sm_id = int(r[2]) if r[2] is not None else None
        if sm_id is None:
            continue
        out.append(
            {
                "fixture_id": af_id,
                "api_football_fixture_id": af_id,
                "sportmonks_fixture_id": sm_id,
                "season": int(r[1]) if r[1] is not None else None,
                "league_id": SPORTMONKS_LEAGUE_ID,
            }
        )
    return out
