"""Resolve real outcomes for MBI odds selections."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "football_intelligence.db"
EXPANDED_PATH = ROOT / "artifacts" / "phase54f6_expanded_dataset" / "expanded_egie_dataset.parquet"
GOALSCORER_PATH = ROOT / "artifacts" / "phase54q_goalscorer_generalization" / "goalscorer_dataset_v3.parquet"


def _mw_label(home: int, away: int) -> str:
    if home > away:
        return "home"
    if away > home:
        return "away"
    return "draw"


def load_outcome_maps() -> dict[str, Any]:
    """Build lookup tables keyed by fixture_id and sportmonks_fixture_id."""
    by_api: dict[str, dict[str, Any]] = {}
    by_sm: dict[str, dict[str, Any]] = {}
    player_anytime: dict[tuple[str, str], bool] = {}
    player_first: dict[tuple[str, str], bool] = {}

    if EXPANDED_PATH.is_file():
        df = pd.read_parquet(EXPANDED_PATH)
        for row in df.itertuples(index=False):
            sm_id = str(int(row.sportmonks_fixture_id))
            api_id = str(int(row.fixture_id)) if pd.notna(row.fixture_id) else None
            payload = {
                "match_winner": _mw_label(int(row.final_score_home), int(row.final_score_away)),
                "first_team_to_score": str(row.label_first_goal_team),
                "over_under": "over_2_5" if int(row.label_over_25) == 1 else "under_2_5",
                "home_team": str(row.home_team_name or row.home_team or ""),
                "away_team": str(row.away_team_name or row.away_team or ""),
            }
            by_sm[sm_id] = payload
            if api_id:
                by_api[api_id] = payload

    if GOALSCORER_PATH.is_file():
        gs = pd.read_parquet(GOALSCORER_PATH, columns=["sportmonks_fixture_id", "player_name", "target_anytime", "target_first_goal"])
        for row in gs.itertuples(index=False):
            key = (str(int(row.sportmonks_fixture_id)), str(row.player_name).strip().lower())
            player_anytime[key] = bool(int(row.target_anytime))
            player_first[key] = bool(int(row.target_first_goal))

    if DB_PATH.is_file():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT f.fixture_id, f.home_team, f.away_team, r.home_goals, r.away_goals
            FROM fixtures f
            JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
            """
        ).fetchall()
        fg_rows = conn.execute(
            """
            SELECT e.fixture_id, e.team, f.home_team, f.away_team
            FROM fixture_goal_events e
            JOIN fixtures f ON f.fixture_id = e.fixture_id
            WHERE e.sort_index = 0
            """
        ).fetchall()
        conn.close()

        first_goal: dict[str, str] = {}
        for r in fg_rows:
            fid = str(int(r["fixture_id"]))
            team = str(r["team"] or "")
            home = str(r["home_team"] or "")
            away = str(r["away_team"] or "")
            if team == home:
                first_goal[fid] = "home"
            elif team == away:
                first_goal[fid] = "away"

        for r in rows:
            fid = str(int(r["fixture_id"]))
            if fid in by_api:
                continue
            hg, ag = int(r["home_goals"]), int(r["away_goals"])
            by_api[fid] = {
                "match_winner": _mw_label(hg, ag),
                "first_team_to_score": first_goal.get(fid),
                "over_under": "over_2_5" if (hg + ag) > 2 else "under_2_5",
                "home_team": str(r["home_team"] or ""),
                "away_team": str(r["away_team"] or ""),
            }

    return {
        "by_api_fixture": by_api,
        "by_sportmonks_fixture": by_sm,
        "player_anytime": player_anytime,
        "player_first": player_first,
    }


def resolve_hit(
    *,
    market_key: str,
    selection: str,
    fixture_key: str,
    source: str,
    outcomes: dict[str, Any],
) -> tuple[bool | None, str | None]:
    """Return (hit, outcome_label) for a selection."""
    api_map = outcomes["by_api_fixture"]
    sm_map = outcomes["by_sportmonks_fixture"]
    fx = sm_map.get(fixture_key) or api_map.get(fixture_key)
    sel = selection.lower().strip()

    if market_key == "match_winner":
        if not fx:
            return None, None
        outcome = fx.get("match_winner")
        alias = {"home_win": "home", "away_win": "away", "1": "home", "2": "away", "x": "draw"}
        sel_n = alias.get(sel, sel)
        return outcome == sel_n, outcome

    if market_key == "first_team_to_score":
        if not fx:
            return None, None
        outcome = fx.get("first_team_to_score")
        if outcome in (None, "none", "no_goal"):
            return None, outcome
        return outcome == sel, outcome

    if market_key == "over_under":
        if not fx:
            return None, None
        outcome = fx.get("over_under")
        sel_n = sel.replace(" ", "_")
        if sel_n in ("over", "yes"):
            sel_n = "over_2_5"
        if sel_n in ("under", "no"):
            sel_n = "under_2_5"
        return outcome == sel_n, outcome

    if market_key == "anytime_goalscorer":
        key = (fixture_key, sel)
        if key in outcomes["player_anytime"]:
            hit = outcomes["player_anytime"][key]
            return hit, "scored" if hit else "not_scored"
        return None, None

    if market_key == "first_goalscorer":
        key = (fixture_key, sel)
        if key in outcomes["player_first"]:
            hit = outcomes["player_first"][key]
            return hit, "first_goal" if hit else "not_first"
        return None, None

    return None, None


def _scores_from_sportmonks_data(data: dict[str, Any]) -> tuple[int | None, int | None]:
    """Parse full-time goals from Sportmonks scores — CURRENT/FT only (not half splits)."""
    home_goals: int | None = None
    away_goals: int | None = None
    id_to_side: dict[int, str] = {}
    for p in data.get("participants") or []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        if pid is not None and loc in ("home", "away"):
            id_to_side[int(pid)] = loc

    priority = {"CURRENT": 0, "FT": 1, "FULL TIME": 2, "FULLTIME": 2}
    best_rank = 999
    for block in data.get("scores") or []:
        if not isinstance(block, dict):
            continue
        desc = str(block.get("description") or "").upper()
        rank = priority.get(desc)
        if rank is None:
            continue
        score = block.get("score") or {}
        if not isinstance(score, dict):
            continue
        try:
            goals = int(score.get("goals")) if score.get("goals") is not None else None
        except (TypeError, ValueError):
            goals = None
        if goals is None:
            continue
        participant = str(score.get("participant") or "").lower()
        pid = block.get("participant_id") or score.get("participant_id")
        side = participant if participant in ("home", "away") else None
        if not side and pid is not None:
            side = id_to_side.get(int(pid))
        if rank < best_rank:
            home_goals, away_goals = 0, 0
            best_rank = rank
        elif rank > best_rank:
            continue
        if side == "home":
            home_goals = goals
        elif side == "away":
            away_goals = goals

    if home_goals is None or away_goals is None:
        return None, None
    return home_goals, away_goals


def enrich_sportmonks_outcomes_from_cache(cache_payload: Any, fixture_key: str, outcomes: dict[str, Any]) -> None:
    """Fill sportmonks outcome map from a finished cache payload when missing."""
    if fixture_key in outcomes["by_sportmonks_fixture"]:
        return
    raw = (cache_payload or {}).get("payload", cache_payload)
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        return
    home_name = ""
    away_name = ""
    for p in data.get("participants") or []:
        if not isinstance(p, dict):
            continue
        meta = p.get("meta") or {}
        loc = str(meta.get("location") or "").lower()
        name = str((p.get("name") or "")).strip()
        if loc == "home":
            home_name = name
        elif loc == "away":
            away_name = name
    hg, ag = _scores_from_sportmonks_data(data)
    if hg is None or ag is None:
        result = parse_match_result(cache_payload, home_team=home_name, away_team=away_name)
        if not result:
            return
        hg = int(result.get("home_goals") or 0)
        ag = int(result.get("away_goals") or 0)
        first = result.get("first_goal_team_side") or result.get("first_goal_team")
    else:
        result = parse_match_result(cache_payload, home_team=home_name, away_team=away_name)
        first = result.get("first_goal_team_side") if result else None
    outcomes["by_sportmonks_fixture"][fixture_key] = {
        "match_winner": _mw_label(hg, ag),
        "first_team_to_score": first,
        "over_under": "over_2_5" if (hg + ag) > 2 else "under_2_5",
        "home_team": home_name,
        "away_team": away_name,
    }
