"""Load API-Football historical World Cup fixtures into SQLite for EGIE."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.api_football_historical_importer import ApiFootballHistoricalImporter
from worldcup_predictor.data_import.models import ImportedMatchRow
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.egie.world_cup.competition_tags import classify_fixture_competition_type
from worldcup_predictor.egie.world_cup.config import (
    API_FOOTBALL_LEAGUE_ID,
    WORLD_CUP_COMPETITION_KEY,
    WORLD_CUP_SEASONS,
)

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_fixture(row: ImportedMatchRow, *, season: int) -> TournamentFixture:
    return TournamentFixture(
        fixture_id=int(row.fixture_id),
        kickoff_time=row.date,
        home_team=row.home_team,
        away_team=row.away_team,
        venue=row.venue or "Unknown",
        city="",
        country="",
        group="",
        round=row.round or "",
        status="FT",
        is_placeholder=False,
        source="live",
        home_goals=row.home_goals,
        away_goals=row.away_goals,
        halftime_home_goals=row.halftime_home_goals,
        halftime_away_goals=row.halftime_away_goals,
        league_id=API_FOOTBALL_LEAGUE_ID,
        season=season,
    )


def _save_odds_snapshot(repo: FootballIntelligenceRepository, row: ImportedMatchRow) -> bool:
    if row.odds_home is None and row.odds_draw is None and row.odds_away is None:
        return False
    if repo.has_odds_snapshot(int(row.fixture_id)):
        return False
    payload = {
        "home": row.odds_home,
        "draw": row.odds_draw,
        "away": row.odds_away,
        "over_2_5": row.over_2_5_odds,
        "under_2_5": row.under_2_5_odds,
        "source": "historical_import",
    }
    repo._conn.execute(
        """
        INSERT INTO odds_snapshots(fixture_id, competition_key, snapshot_at, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (int(row.fixture_id), WORLD_CUP_COMPETITION_KEY, _utc_now(), json.dumps(payload)),
    )
    return True


def import_and_load_sqlite(
    *,
    seasons: tuple[int, ...] | None = None,
    settings: Settings | None = None,
    fetch_odds: bool = True,
) -> dict[str, Any]:
    """Import WC history from API-Football and persist to SQLite."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        comp = get_competition(WORLD_CUP_COMPETITION_KEY)
        repo.upsert_competition(comp)
    except KeyError:
        pass

    importer = ApiFootballHistoricalImporter(settings, fetch_odds=fetch_odds)
    active_seasons = list(seasons or WORLD_CUP_SEASONS)
    result_summary: dict[str, Any] = {
        "seasons": active_seasons,
        "api_configured": importer.is_configured,
        "fixtures_upserted": 0,
        "results_upserted": 0,
        "odds_saved": 0,
        "per_season": {},
        "errors": [],
    }

    if not importer.is_configured:
        result_summary["errors"].append("API_FOOTBALL_KEY not configured")
        return result_summary

    for season in active_seasons:
        partial = importer.import_fixtures(league_id=API_FOOTBALL_LEAGUE_ID, season=season)
        season_stats = {"imported": 0, "upserted": 0, "results": 0, "odds": 0}
        for row in partial.rows:
            tf = _row_to_fixture(row, season=season)
            if repo.upsert_fixture(tf, competition_key=WORLD_CUP_COMPETITION_KEY, league_id=API_FOOTBALL_LEAGUE_ID, season=season):
                season_stats["upserted"] += 1
                result_summary["fixtures_upserted"] += 1
                comp_type = classify_fixture_competition_type(
                    round_name=row.round,
                    league_id=API_FOOTBALL_LEAGUE_ID,
                    competition_key=WORLD_CUP_COMPETITION_KEY,
                )
                repo._conn.execute(
                    "UPDATE fixtures SET competition_type = ? WHERE fixture_id = ?",
                    (comp_type, int(row.fixture_id)),
                )
            if repo.upsert_fixture_result(tf, competition_key=WORLD_CUP_COMPETITION_KEY):
                season_stats["results"] += 1
                result_summary["results_upserted"] += 1
            if _save_odds_snapshot(repo, row):
                season_stats["odds"] += 1
                result_summary["odds_saved"] += 1
            season_stats["imported"] += 1
        result_summary["per_season"][str(season)] = season_stats
        result_summary["errors"].extend(partial.api_errors)

    repo._conn.commit()
    return result_summary


def count_wc_fixtures(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    row = repo._conn.execute(
        "SELECT COUNT(1) FROM fixtures WHERE competition_key = ?",
        (WORLD_CUP_COMPETITION_KEY,),
    ).fetchone()
    return int(row[0] or 0) if row else 0
