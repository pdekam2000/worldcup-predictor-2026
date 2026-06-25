"""Fixture identity mapping audit for EGIE Premier League backtest cohort."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.competitions import PREMIER_LEAGUE
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.config import PROVIDER_API_FOOTBALL, PROVIDER_SPORTMONKS
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository

_FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")
_EGIE_RESOURCES = ("events", "lineups", "injuries", "fixture_statistics")
_SM_RESOURCES = ("xg", "fixture_statistics", "fixtures")


def _list_pl_fixtures(repo: FootballIntelligenceRepository, *, limit: int | None = None) -> list[dict[str, Any]]:
    ph = ",".join("?" * len(_FINISHED))
    q = f"""
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status
        FROM fixtures
        WHERE competition_key = 'premier_league' AND is_placeholder = 0
          AND status IN ({ph})
        ORDER BY kickoff_utc ASC
    """
    params: list[Any] = list(_FINISHED)
    if limit:
        q += " LIMIT ?"
        params.append(int(limit))
    return [dict(r) for r in repo._conn.execute(q, params).fetchall()]


def _wc_odds_fixture_ids(repo: FootballIntelligenceRepository) -> set[int]:
    rows = repo._conn.execute(
        """
        SELECT DISTINCT o.fixture_id
        FROM odds_snapshots o
        LEFT JOIN fixtures f ON f.fixture_id = o.fixture_id
        WHERE f.fixture_id IS NULL OR f.competition_key != 'premier_league'
        """
    ).fetchall()
    return {int(r[0]) for r in rows if r[0]}


def audit_pl_fixture_mapping(
    *,
    settings: Settings | None = None,
    limit: int | None = 400,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = EgieRawStoreRepository(settings)
    fixtures = _list_pl_fixtures(repo, limit=limit)
    wc_odds_only = _wc_odds_fixture_ids(repo)

    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}

    for fx in fixtures:
        fid = int(fx["fixture_id"])
        sm_row = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(fid)
        sm_id = int(sm_row["sportmonks_fixture_id"]) if sm_row and sm_row.get("sportmonks_fixture_id") else None

        af_cov = {
            res: bool(
                store.get_latest_raw(
                    provider=PROVIDER_API_FOOTBALL,
                    resource_type=res,
                    fixture_id=fid,
                )
            )
            for res in _EGIE_RESOURCES
        }
        sm_cov = {
            res: bool(
                store.get_latest_raw(
                    provider=PROVIDER_SPORTMONKS,
                    resource_type=res,
                    fixture_id=fid,
                )
            )
            for res in _SM_RESOURCES
        }
        has_pl_odds = bool(
            repo._conn.execute(
                "SELECT 1 FROM odds_snapshots o JOIN fixtures f ON f.fixture_id = o.fixture_id "
                "WHERE o.fixture_id = ? AND f.competition_key = 'premier_league' LIMIT 1",
                (fid,),
            ).fetchone()
        )
        has_xg_sqlite = bool(repo.has_xg_snapshot(fid))

        if sm_id and (sm_cov.get("xg") or has_xg_sqlite):
            mapping_status = "sportmonks_mapped_with_xg"
        elif sm_id:
            mapping_status = "sportmonks_mapped_no_xg_store"
        elif any(af_cov.values()):
            mapping_status = "api_football_only"
        else:
            mapping_status = "unmapped"

        if has_pl_odds:
            mapping_status += "+pl_odds"
        elif fid in wc_odds_only:
            mapping_status += "+wc_odds_mismatch"

        status_counts[mapping_status] = status_counts.get(mapping_status, 0) + 1

        rows.append(
            {
                "fixture_id": fid,
                "api_football_fixture_id": fid,
                "sportmonks_fixture_id": sm_id,
                "league_id": PREMIER_LEAGUE.league_id,
                "season": PREMIER_LEAGUE.season,
                "date": fx.get("kickoff_utc"),
                "home_team": fx.get("home_team"),
                "away_team": fx.get("away_team"),
                "mapping_status": mapping_status,
                "api_football_raw": af_cov,
                "sportmonks_raw": sm_cov,
                "has_pl_odds_snapshot": has_pl_odds,
                "has_xg_sqlite": has_xg_sqlite,
            }
        )

    mapped_sm = sum(1 for r in rows if r.get("sportmonks_fixture_id"))
    pl_odds = sum(1 for r in rows if r.get("has_pl_odds_snapshot"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "competition_key": "premier_league",
        "fixture_count": len(rows),
        "mapping_success_rate_pct": round(100 * mapped_sm / len(rows), 2) if rows else 0.0,
        "sportmonks_mapped_count": mapped_sm,
        "pl_odds_aligned_count": pl_odds,
        "wc_odds_orphan_fixture_ids": sorted(wc_odds_only)[:20],
        "mapping_status_counts": status_counts,
        "fixtures": rows,
    }
