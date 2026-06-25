"""Map API-Football fixtures to Sportmonks / internal fixtures."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_bridge.models import FixtureBridge
from worldcup_predictor.egie.goalscorer_bridge.team_mapper import teams_match_fixture
from worldcup_predictor.egie.goalscorer_odds_acquisition.inventory import DB_PATH, _scan_api_football_payload
from worldcup_predictor.providers.sportmonks_fixture_lookup import team_names_match
from worldcup_predictor.providers.sportmonks_provider import WORLD_CUP_2026_LEAGUE_ID

import re

_GS_MARKET = re.compile(r"(anytime|first|last)\s+goal\s+scorer", re.I)

_SPORTMONKS_CACHE_ROOTS = (
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
)


def _load_sportmonks_wc_index() -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    seen: set[int] = set()
    for root in _SPORTMONKS_CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            try:
                lid = int(data.get("league_id") or 0)
            except (TypeError, ValueError):
                continue
            if lid != WORLD_CUP_2026_LEAGUE_ID:
                continue
            fid = int(data.get("id") or 0)
            if fid in seen:
                continue
            seen.add(fid)
            home = away = None
            home_id = away_id = None
            for part in data.get("participants") or []:
                if not isinstance(part, dict):
                    continue
                loc = str((part.get("meta") or {}).get("location") or "").lower()
                name = str(part.get("name") or "")
                pid = part.get("id")
                if loc == "home":
                    home, home_id = name, pid
                elif loc == "away":
                    away, away_id = name, pid
            lineups = data.get("lineups") or []
            index.append(
                {
                    "sportmonks_fixture_id": fid,
                    "home_team": home,
                    "away_team": away,
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "match_date": str(data.get("starting_at") or "")[:10],
                    "lineups_count": len(lineups),
                    "cache_path": str(path),
                }
            )
    return index


def load_api_goalscorer_fixtures() -> list[dict[str, Any]]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    seen: set[int] = set()
    fixtures: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT o.fixture_id, o.payload_json, f.home_team, f.away_team, f.home_team_id,
               f.away_team_id, f.kickoff_utc, f.season, f.competition_key, f.status
        FROM odds_snapshots o
        JOIN fixtures f ON f.fixture_id = o.fixture_id
        """
    ).fetchall():
        fid, payload_json, home, away, home_id, away_id, kickoff, season, comp, status = row
        if fid in seen:
            continue
        seen.add(fid)
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        rows, _, _ = _scan_api_football_payload(payload, fixture_id=int(fid))
        gs_rows = [r for r in rows if _GS_MARKET.search(str(r.get("market") or ""))]
        if not gs_rows:
            continue
        fixtures.append(
            {
                "api_football_fixture_id": int(fid),
                "internal_fixture_id": int(fid),
                "home_team": str(home or ""),
                "away_team": str(away or ""),
                "home_team_id": int(home_id) if home_id else None,
                "away_team_id": int(away_id) if away_id else None,
                "kickoff_utc": kickoff,
                "season": season,
                "competition_key": comp,
                "status": status,
                "gs_selection_count": len(gs_rows),
            }
        )
    conn.close()
    return fixtures


def build_fixture_bridges() -> list[FixtureBridge]:
    api_fixtures = load_api_goalscorer_fixtures()
    sm_index = _load_sportmonks_wc_index()
    bridges: list[FixtureBridge] = []

    for fx in api_fixtures:
        api_id = int(fx["api_football_fixture_id"])
        home = fx["home_team"]
        away = fx["away_team"]
        date = str(fx.get("kickoff_utc") or "")[:10]

        best: dict[str, Any] | None = None
        method = "unmapped"
        confidence = "UNMAPPED"

        # exact date + both teams
        for sm in sm_index:
            if sm["match_date"] != date:
                continue
            if teams_match_fixture(
                home_team=home,
                away_team=away,
                candidate_home=sm.get("home_team"),
                candidate_away=sm.get("away_team"),
            ):
                best = sm
                method = "cache_date_teams"
                confidence = "HIGH"
                break

        # date +/- fuzzy: one team exact on date
        if best is None:
            for sm in sm_index:
                if sm["match_date"] != date:
                    continue
                home_ok = team_names_match(home, sm.get("home_team") or "")
                away_ok = team_names_match(away, sm.get("away_team") or "")
                if home_ok or away_ok:
                    best = sm
                    method = "cache_date_partial_team"
                    confidence = "MEDIUM"
                    break

        # same teams different date (group stage rematch edge)
        if best is None:
            for sm in sm_index:
                if teams_match_fixture(
                    home_team=home,
                    away_team=away,
                    candidate_home=sm.get("home_team"),
                    candidate_away=sm.get("away_team"),
                ):
                    best = sm
                    method = "cache_teams_date_mismatch"
                    confidence = "LOW"
                    break

        bridges.append(
            FixtureBridge(
                api_football_fixture_id=api_id,
                internal_fixture_id=api_id,
                sportmonks_fixture_id=int(best["sportmonks_fixture_id"]) if best else None,
                home_team=home,
                away_team=away,
                home_team_id=int(best["home_team_id"]) if best and best.get("home_team_id") else fx.get("home_team_id"),
                away_team_id=int(best["away_team_id"]) if best and best.get("away_team_id") else fx.get("away_team_id"),
                league=str(fx.get("competition_key") or "world_cup_2026"),
                season=int(fx["season"]) if fx.get("season") else None,
                match_date=date or None,
                status=str(fx.get("status") or ""),
                bridge_confidence=confidence,  # type: ignore[arg-type]
                bridge_method=method,
                sportmonks_lineups_available=bool(best and int(best.get("lineups_count") or 0) >= 20),
                notes="" if best else "no_sportmonks_cache_match",
            )
        )
    return bridges
