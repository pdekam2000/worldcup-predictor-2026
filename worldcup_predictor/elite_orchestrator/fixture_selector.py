"""Part B — upcoming fixture selection for shadow runtime."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.elite_orchestrator.shadow_config import DEFAULT_COMPETITIONS, LEAGUE_MAP, UEFA_LEAGUE_IDS

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "football_intelligence.db"

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fixture_row(
    *,
    fixture_id: int,
    sportmonks_fixture_id: int | None,
    competition_key: str,
    league_id: int | None,
    home_team: str,
    away_team: str,
    kickoff_utc: str,
    source: str,
) -> dict[str, Any]:
    return {
        "fixture_id": int(fixture_id),
        "sportmonks_fixture_id": sportmonks_fixture_id,
        "competition_key": competition_key,
        "league_id": league_id,
        "home_team": home_team,
        "away_team": away_team,
        "kickoff_utc": kickoff_utc,
        "source": source,
    }


def select_from_db(
    *,
    days_ahead: int = 7,
    limit: int = 50,
    league_id: int | None = None,
    competitions: tuple[str, ...] = DEFAULT_COMPETITIONS,
) -> list[dict[str, Any]]:
    """World Cup and other SQLite upcoming fixtures."""
    repo = FootballIntelligenceRepository()
    now = _utc_now()
    horizon = (now + timedelta(days=days_ahead)).replace(tzinfo=None).isoformat()
    rows: list[dict[str, Any]] = []

    for comp in competitions:
        upcoming = repo.list_upcoming_fixtures(comp, season=2026 if "world_cup" in comp else None, limit=limit)
        for fx in upcoming:
            ko = fx.get("kickoff_utc")
            if ko and ko > horizon:
                continue
            sm_id = fx.get("sportmonks_fixture_id")
            lid = league_id or (732 if "world_cup" in comp else None)
            if league_id and lid != league_id:
                continue
            rows.append(
                _fixture_row(
                    fixture_id=int(fx["fixture_id"]),
                    sportmonks_fixture_id=int(sm_id) if sm_id else None,
                    competition_key=str(comp),
                    league_id=lid,
                    home_team=str(fx.get("home_team") or ""),
                    away_team=str(fx.get("away_team") or ""),
                    kickoff_utc=str(ko),
                    source="sqlite_upcoming",
                )
            )
    repo.close()
    return rows[:limit]


def select_uefa_from_enrichment(
    *,
    days_ahead: int = 7,
    limit: int = 50,
    league_id: int | None = None,
) -> list[dict[str, Any]]:
    """UEFA fixtures from sportmonks enrichment with future kickoff in payload."""
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = _utc_now()
    horizon = now + timedelta(days=days_ahead)
    rows: list[dict[str, Any]] = []

    for row in conn.execute(
        "SELECT sportmonks_fixture_id, fixture_id_api_football, league_id, raw_json FROM sportmonks_fixture_enrichment WHERE status='ok'"
    ):
        lid = int(row["league_id"] or 0)
        if league_id and lid != league_id:
            continue
        if league_id is None and lid not in UEFA_LEAGUE_IDS and lid != 732:
            continue
        try:
            payload = json.loads(row["raw_json"])
        except json.JSONDecodeError:
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        ko = _parse_kickoff(str(data.get("starting_at") or ""))
        if not ko or ko <= now or ko > horizon:
            continue
        state = int(data.get("state_id") or 0)
        if state not in (1, 2, 3, 4, 5, 11):  # not started / scheduled
            continue
        participants = data.get("participants") or []
        home = away = ""
        for p in participants:
            loc = str((p.get("meta") or {}).get("location") or "").lower()
            name = str(p.get("name") or "")
            if loc == "home":
                home = name
            elif loc == "away":
                away = name
        api_fid = row["fixture_id_api_football"]
        rows.append(
            _fixture_row(
                fixture_id=int(api_fid or row["sportmonks_fixture_id"]),
                sportmonks_fixture_id=int(row["sportmonks_fixture_id"]),
                competition_key=LEAGUE_MAP.get(lid, f"league_{lid}"),
                league_id=lid,
                home_team=home,
                away_team=away,
                kickoff_utc=ko.isoformat(),
                source="sportmonks_enrichment",
            )
        )
    conn.close()
    rows.sort(key=lambda r: r.get("kickoff_utc") or "")
    return rows[:limit]


def select_fixtures_by_ids(fixture_ids: list[int]) -> list[dict[str, Any]]:
    """Resolve fixture metadata for queued PredOps shadow analysis."""
    if not fixture_ids or not DB_PATH.is_file():
        return []
    wanted = {int(x) for x in fixture_ids if int(x) > 0}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows: list[dict[str, Any]] = []
    for fid in sorted(wanted):
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        if not fx:
            continue
        rows.append(
            _fixture_row(
                fixture_id=int(fx["fixture_id"]),
                sportmonks_fixture_id=int(fx["sportmonks_fixture_id"]) if fx["sportmonks_fixture_id"] else None,
                competition_key=str(fx["competition_key"] or "unknown"),
                league_id=None,
                home_team=str(fx["home_team"] or ""),
                away_team=str(fx["away_team"] or ""),
                kickoff_utc=str(fx["kickoff_utc"] or ""),
                source="queue_fixture_lookup",
            )
        )
    conn.close()
    return rows


def select_upcoming_fixtures(
    *,
    days_ahead: int = 7,
    limit: int = 50,
    league_id: int | None = None,
    include_uefa: bool = True,
) -> list[dict[str, Any]]:
    """Merge WC DB upcoming + UEFA enrichment; dedupe by fixture_id."""
    merged: dict[int, dict[str, Any]] = {}
    for fx in select_from_db(days_ahead=days_ahead, limit=limit, league_id=league_id):
        merged[int(fx["fixture_id"])] = fx
    if include_uefa:
        for fx in select_uefa_from_enrichment(days_ahead=days_ahead, limit=limit, league_id=league_id):
            fid = int(fx["fixture_id"])
            if fid not in merged:
                merged[fid] = fx
    out = sorted(merged.values(), key=lambda r: r.get("kickoff_utc") or "")
    return out[:limit]
