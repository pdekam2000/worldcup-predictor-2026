"""Bridge UEFA Sportmonks fixtures into SQLite for EGIE feature builder."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.egie.uefa_club.config import UEFA_CLUB_LEAGUES
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import uefa_data_root
from worldcup_predictor.egie.uefa_club.feature_extractors import _fixture_data, parse_uefa_goal_events

logger = logging.getLogger(__name__)

_STATUS_MAP = {5: "FT", 7: "AET", 8: "PEN"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_uefa_competitions(repo: FootballIntelligenceRepository) -> None:
    for league in UEFA_CLUB_LEAGUES:
        try:
            comp = get_competition(league.key)
            repo.upsert_competition(comp)
        except KeyError:
            repo._conn.execute(
                """
                INSERT INTO competitions(key, name, league_id, season, competition_type,
                    supports_groups, supports_table, updated_at)
                VALUES (?, ?, ?, 2024, 'cup', 0, 0, ?)
                ON CONFLICT(key) DO UPDATE SET name=excluded.name, league_id=excluded.league_id
                """,
                (league.key, league.name, league.sportmonks_league_id, _utc_now()),
            )
    repo._conn.commit()


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _goal_events_for_sqlite(
    payload: Any,
    *,
    home_team_id: int | None,
    away_team_id: int | None,
    home_team: str,
    away_team: str,
) -> list[dict[str, Any]]:
    raw = _fixture_data(payload)
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for g in parse_uefa_goal_events(raw):
        side = g.get("scoring_side")
        team_name = home_team if side == "home" else away_team if side == "away" else home_team
        kind = g.get("goal_kind") or "goal"
        detail = "Own Goal" if kind == "own_goal" else "Penalty" if kind == "penalty" else "Goal"
        out.append(
            {
                "minute": g.get("minute"),
                "team": team_name,
                "team_id": g.get("team_id"),
                "detail": detail,
                "sort_index": len(out),
            }
        )
    return out


def sync_uefa_fixtures_to_sqlite(
    fixtures: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    _ensure_uefa_competitions(repo)
    cache_root = uefa_data_root(settings) / "egie" / "uefa_club" / "raw"
    legacy_root = uefa_data_root(settings) / "data" / "egie" / "uefa_club" / "raw"
    upserted = 0
    events_saved = 0

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        if sm_id <= 0:
            continue
        cache = cache_root / f"{sm_id}.json"
        if not cache.is_file():
            cache = legacy_root / f"{sm_id}.json"
        payload = None
        if cache.is_file():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8")).get("payload")
            except (json.JSONDecodeError, OSError):
                payload = None

        kickoff = _parse_kickoff(str(fx.get("kickoff_utc") or ""))
        state_id = int(fx.get("state_id") or 5)
        status = _STATUS_MAP.get(state_id, "FT")
        comp = str(fx.get("competition_key") or "champions_league")
        home = str(fx.get("home_team") or "")
        away = str(fx.get("away_team") or "")

        kickoff = kickoff or datetime.now(timezone.utc).replace(tzinfo=None)
        tf = TournamentFixture(
            fixture_id=sm_id,
            kickoff_time=kickoff,
            home_team=home,
            away_team=away,
            venue="",
            city="",
            country="",
            group="",
            round=str(fx.get("fixture_name") or ""),
            status=status,
            is_placeholder=False,
            source="live",
            home_team_id=fx.get("home_team_id"),
            away_team_id=fx.get("away_team_id"),
            league_id=int(fx.get("league_id") or 0) or None,
            season=int(fx.get("season_id") or 0) if fx.get("season_id") else None,
        )
        if repo.upsert_fixture(
            tf,
            competition_key=comp,
            league_id=int(fx.get("league_id") or 0) or None,
            season=int(fx.get("season_id") or 0) if fx.get("season_id") else None,
        ):
            upserted += 1

        if payload:
            events = _goal_events_for_sqlite(
                payload,
                home_team_id=fx.get("home_team_id"),
                away_team_id=fx.get("away_team_id"),
                home_team=home,
                away_team=away,
            )
            if events and repo.replace_fixture_goal_events(sm_id, events):
                events_saved += 1

    return {"fixtures_upserted": upserted, "fixtures_with_goal_events": events_saved}
