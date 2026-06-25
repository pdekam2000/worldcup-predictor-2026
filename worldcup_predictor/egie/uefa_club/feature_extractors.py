"""Parse Sportmonks UEFA fixture payloads into EGIE provider fields."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.providers.sportmonks_xg_extraction import parse_sportmonks_xg_match

# Sportmonks v3 event types (verified on UEFA club cache, Phase API-I).
GOAL_TYPE_ID = 14
OWN_GOAL_TYPE_ID = 15
PENALTY_GOAL_TYPE_ID = 16
MISSED_PENALTY_TYPE_ID = 17
PENALTY_SHOOTOUT_GOAL_TYPE_ID = 23

SCORING_EVENT_TYPE_IDS = {
    GOAL_TYPE_ID,
    OWN_GOAL_TYPE_ID,
    PENALTY_GOAL_TYPE_ID,
    PENALTY_SHOOTOUT_GOAL_TYPE_ID,
}


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fixture_data(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload.get("response"), dict):
        return payload["response"]
    if payload.get("id"):
        return payload
    inner = payload.get("parsed") or payload.get("raw_fixture")
    if isinstance(inner, dict) and inner.get("id"):
        return inner
    return None


def parse_uefa_xg(payload: Any) -> dict[str, float | None]:
    raw = _fixture_data(payload)
    hx = ax = None
    if raw:
        id_to_side: dict[int, str] = {}
        for part in raw.get("participants") or []:
            if isinstance(part, dict) and part.get("id"):
                loc = str((part.get("meta") or {}).get("location") or "").lower()
                if loc in ("home", "away"):
                    id_to_side[int(part["id"])] = loc
        home_xg = away_xg = None
        block = raw.get("xgfixture") or raw.get("xGFixture") or []
        if isinstance(block, list):
            for row in block:
                if not isinstance(row, dict):
                    continue
                tid = row.get("type_id")
                if tid != 5304:
                    continue
                val = _float((row.get("data") or {}).get("value"))
                if val is None:
                    continue
                loc = str(row.get("location") or "").lower()
                if loc not in ("home", "away"):
                    pid = row.get("participant_id")
                    if pid is not None:
                        loc = id_to_side.get(int(pid), "")
                if loc == "home":
                    home_xg = val
                elif loc == "away":
                    away_xg = val
        hx, ax = home_xg, away_xg
        if hx is None or ax is None:
            parsed = parse_sportmonks_xg_match(raw)
            team = parsed.get("team") or {}
            if hx is None:
                hx = _float(team.get("home_xg"))
            if ax is None:
                ax = _float(team.get("away_xg"))
    diff = round(hx - ax, 4) if hx is not None and ax is not None else None
    return {
        "home_xg": hx,
        "away_xg": ax,
        "xg_diff": diff,
        "home_xg_for": hx,
        "away_xg_for": ax,
    }


def parse_uefa_pressure(payload: Any) -> dict[str, float | None]:
    raw = _fixture_data(payload)
    if not raw:
        return {"home_pressure": None, "away_pressure": None, "pressure_diff": None}
    pressure = raw.get("pressure")
    if isinstance(pressure, list) and pressure:
        home_p = away_p = None
        for block in pressure:
            if not isinstance(block, dict):
                continue
            loc = str(block.get("participant_id") or block.get("location") or "").lower()
            val = _float(block.get("value") or block.get("pressure"))
            if "home" in loc:
                home_p = val
            elif "away" in loc:
                away_p = val
        if home_p is None and len(pressure) >= 2:
            home_p = _float(pressure[0].get("value") if isinstance(pressure[0], dict) else None)
            away_p = _float(pressure[1].get("value") if isinstance(pressure[1], dict) else None)
        diff = round(home_p - away_p, 4) if home_p is not None and away_p is not None else None
        return {
            "home_pressure": home_p,
            "away_pressure": away_p,
            "pressure_diff": diff,
            "pressure_index_home": home_p,
            "pressure_index_away": away_p,
        }
    # flat statistics array (Sportmonks v3)
    stats = raw.get("statistics")
    if isinstance(stats, list) and stats and isinstance(stats[0], dict) and stats[0].get("location"):
        home_p = away_p = None
        for entry in stats:
            if not isinstance(entry, dict):
                continue
            label = str((entry.get("type") or {}).get("name") or "").lower()
            if "possession" not in label:
                continue
            val = _float((entry.get("data") or {}).get("value"))
            loc = str(entry.get("location") or "").lower()
            if loc == "home":
                home_p = (val / 100.0) if val and val > 1 else val
            elif loc == "away":
                away_p = (val / 100.0) if val and val > 1 else val
        if home_p is not None or away_p is not None:
            diff = round((home_p or 0) - (away_p or 0), 4)
            return {
                "home_pressure": home_p,
                "away_pressure": away_p,
                "pressure_diff": diff,
                "pressure_index_home": home_p,
                "pressure_index_away": away_p,
            }
    # nested statistics blocks
    if isinstance(stats, list):
        home_p = away_p = None
        for block in stats:
            if not isinstance(block, dict):
                continue
            loc = str(block.get("location") or "").lower()
            for metric in block.get("data") or []:
                if not isinstance(metric, dict):
                    continue
                label = str((metric.get("type") or {}).get("name") or metric.get("type") or "").lower()
                if "possession" in label:
                    val = _float(metric.get("value"))
                    if loc == "home":
                        home_p = (val / 100.0) if val and val > 1 else val
                    elif loc == "away":
                        away_p = (val / 100.0) if val and val > 1 else val
        if home_p is not None or away_p is not None:
            diff = round((home_p or 0) - (away_p or 0), 4)
            return {
                "home_pressure": home_p,
                "away_pressure": away_p,
                "pressure_diff": diff,
                "pressure_index_home": home_p,
                "pressure_index_away": away_p,
            }
    # fallback xG share proxy
    xg = parse_uefa_xg(raw)
    hx, ax = xg.get("home_xg"), xg.get("away_xg")
    if hx is not None and ax is not None and (hx + ax) > 0:
        hp = round(hx / (hx + ax), 4)
        ap = round(ax / (hx + ax), 4)
        return {
            "home_pressure": hp,
            "away_pressure": ap,
            "pressure_diff": round(hp - ap, 4),
            "pressure_index_home": hp,
            "pressure_index_away": ap,
        }
    return {"home_pressure": None, "away_pressure": None, "pressure_diff": None}


def _implied_from_decimal(odds: float | None) -> float | None:
    if odds is None or odds <= 1.0:
        return None
    return round(1.0 / odds, 4)


def parse_uefa_odds(payload: Any) -> dict[str, float | None]:
    raw = _fixture_data(payload)
    out = {
        "implied_home": None,
        "implied_draw": None,
        "implied_away": None,
        "odds_implied_home": None,
        "odds_implied_draw": None,
        "odds_implied_away": None,
        "first_goal_odds": None,
        "odds_movement": None,
    }
    if not raw:
        return out
    odds = raw.get("odds")
    if not isinstance(odds, list):
        return out
    home_dec = draw_dec = away_dec = None
    for entry in odds:
        if not isinstance(entry, dict):
            continue
        market = str((entry.get("market") or {}).get("name") or entry.get("name") or "").lower()
        label = str(entry.get("label") or entry.get("name") or "").lower()
        value = _float(entry.get("value") or entry.get("dp3") or entry.get("odd"))
        if "fulltime" in market or "full time" in market or "1x2" in market or "match winner" in market:
            if label in ("home", "1"):
                home_dec = value
            elif label in ("draw", "x"):
                draw_dec = value
            elif label in ("away", "2"):
                away_dec = value
        if "first goal" in market or "first team to score" in market:
            if label in ("home", "1"):
                out["first_goal_odds"] = _implied_from_decimal(value)
    out["implied_home"] = out["odds_implied_home"] = _implied_from_decimal(home_dec)
    out["implied_draw"] = out["odds_implied_draw"] = _implied_from_decimal(draw_dec)
    out["implied_away"] = out["odds_implied_away"] = _implied_from_decimal(away_dec)
    return out


def parse_uefa_predictions(payload: Any) -> dict[str, float | None]:
    raw = _fixture_data(payload)
    out = {
        "sportmonks_home_win": None,
        "sportmonks_draw": None,
        "sportmonks_away_win": None,
    }
    if not raw:
        return out
    preds = raw.get("predictions")
    if not isinstance(preds, list):
        return out
    for p in preds:
        if not isinstance(p, dict):
            continue
        tname = str((p.get("type") or {}).get("name") or "").lower()
        probs = p.get("predictions") if isinstance(p.get("predictions"), dict) else p
        if not isinstance(probs, dict):
            continue
        if "fulltime" in tname or "1x2" in tname or not tname:
            out["sportmonks_home_win"] = _float(probs.get("home") or probs.get("home_win"))
            out["sportmonks_draw"] = _float(probs.get("draw"))
            out["sportmonks_away_win"] = _float(probs.get("away") or probs.get("away_win"))
    return out


def parse_uefa_lineups(payload: Any) -> dict[str, float | None]:
    raw = _fixture_data(payload)
    out = {
        "lineup_strength_home": None,
        "lineup_strength_away": None,
        "lineup_stability": None,
        "missing_key_players": None,
    }
    if not raw:
        return out
    lineups = raw.get("lineups")
    if not isinstance(lineups, list):
        return out
    strengths: list[float] = []
    missing = 0
    for lu in lineups[:2]:
        if not isinstance(lu, dict):
            continue
        players = lu.get("details") or lu.get("players") or []
        n = len(players) if isinstance(players, list) else 0
        strengths.append(round(min(1.0, n / 11.0), 4) if n else 0.0)
        if n < 9:
            missing += 1
    if strengths:
        out["lineup_strength_home"] = strengths[0]
        out["lineup_strength_away"] = strengths[1] if len(strengths) > 1 else None
        out["lineup_stability"] = round(sum(strengths) / len(strengths), 4)
        out["missing_key_players"] = float(missing)
    return out


def build_participant_maps(raw: dict[str, Any]) -> tuple[dict[int, str], dict[int, str], dict[str, int]]:
    """Map participant_id -> home/away side and team name."""
    id_to_side: dict[int, str] = {}
    id_to_name: dict[int, str] = {}
    side_to_id: dict[str, int] = {}
    for p in raw.get("participants") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = int(p["id"])
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        if loc in ("home", "away"):
            id_to_side[pid] = loc
            side_to_id[loc] = pid
        name = str(p.get("name") or "").strip()
        if name:
            id_to_name[pid] = name
    return id_to_side, id_to_name, side_to_id


def _event_minute(ev: dict[str, Any]) -> int | None:
    minute = ev.get("minute")
    extra = ev.get("extra_minute") or 0
    try:
        return int(minute or 0) + int(extra or 0)
    except (TypeError, ValueError):
        return None


def _goal_kind(type_id: int | None, type_name: str) -> str | None:
    if type_id == GOAL_TYPE_ID or type_name == "goal":
        return "goal"
    if type_id == PENALTY_GOAL_TYPE_ID or type_name == "penalty":
        return "penalty"
    if type_id == OWN_GOAL_TYPE_ID or "own goal" in type_name:
        return "own_goal"
    if type_id == PENALTY_SHOOTOUT_GOAL_TYPE_ID or "penalty shootout goal" in type_name:
        return "penalty_shootout"
    if "goal" in type_name and "miss" not in type_name and "shootout" not in type_name:
        return "goal"
    return None


def _scoring_side_for_event(
    ev: dict[str, Any],
    *,
    goal_kind: str,
    id_to_side: dict[int, str],
) -> str | None:
    pid = ev.get("participant_id")
    if pid is None:
        return None
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return None
    side = id_to_side.get(pid_i)
    if not side:
        return None
    if goal_kind == "own_goal":
        return "away" if side == "home" else "home"
    return side


def _is_scoring_event(ev: dict[str, Any]) -> bool:
    if ev.get("rescinded") is True:
        return False
    type_id = ev.get("type_id")
    type_name = str((ev.get("type") or {}).get("name") or "").lower()
    if type_id in SCORING_EVENT_TYPE_IDS:
        return True
    return _goal_kind(type_id, type_name) is not None


def parse_uefa_goal_events(payload: Any, *, include_shootout: bool = False) -> list[dict[str, Any]]:
    raw = _fixture_data(payload)
    if not raw:
        return []
    events = raw.get("events")
    if not isinstance(events, list):
        return []
    id_to_side, id_to_name, _ = build_participant_maps(raw)
    goals: list[dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict) or not _is_scoring_event(ev):
            continue
        type_id = ev.get("type_id")
        type_name = str((ev.get("type") or {}).get("name") or "").lower()
        kind = _goal_kind(type_id, type_name)
        if not kind:
            continue
        if kind == "penalty_shootout" and not include_shootout:
            continue
        minute_i = _event_minute(ev)
        pid = ev.get("participant_id")
        side = _scoring_side_for_event(ev, goal_kind=kind, id_to_side=id_to_side)
        goals.append(
            {
                "minute": minute_i,
                "team_id": pid,
                "participant_id": pid,
                "type_id": type_id,
                "goal_kind": kind,
                "scoring_side": side,
                "team_name": id_to_name.get(int(pid)) if pid is not None else None,
                "player_name": ev.get("player_name"),
                "result": ev.get("result"),
                "info": ev.get("info"),
                "addition": ev.get("addition"),
                "sort_order": ev.get("sort_order") or 0,
                "var_confirmed": "var" in str(ev.get("info") or "").lower()
                or "var" in str(ev.get("addition") or "").lower(),
            }
        )
    goals.sort(key=lambda g: (g.get("minute") is None, g.get("minute") or 999, g.get("sort_order") or 0))
    return goals


def _scores_from_fixture(raw: dict[str, Any], id_to_side: dict[int, str]) -> tuple[int, int]:
    home_goals = away_goals = 0
    for block in raw.get("scores") or []:
        if not isinstance(block, dict):
            continue
        desc = str(block.get("description") or "").upper()
        if desc not in ("CURRENT", "FT", "2ND_HALF", "FULL TIME"):
            continue
        score = block.get("score") or {}
        if not isinstance(score, dict):
            continue
        goals_raw = score.get("goals")
        try:
            goals = int(goals_raw) if goals_raw is not None else None
        except (TypeError, ValueError):
            goals = None
        if goals is None:
            continue
        participant = str(score.get("participant") or "").lower()
        pid = score.get("participant_id")
        side = participant if participant in ("home", "away") else None
        if not side and pid is not None:
            side = id_to_side.get(int(pid))
        if side == "home":
            home_goals = goals
        elif side == "away":
            away_goals = goals
    return home_goals, away_goals


def _goals_tally_from_events(goals: list[dict[str, Any]]) -> tuple[int, int]:
    home = away = 0
    for g in goals:
        side = g.get("scoring_side")
        if side == "home":
            home += 1
        elif side == "away":
            away += 1
    return home, away


def parse_match_result(payload: Any, *, home_team: str, away_team: str) -> dict[str, Any]:
    raw = _fixture_data(payload)
    home_goals = away_goals = 0
    first_goal_team: str | None = None
    first_goal_team_side: str | None = None
    first_goal_team_id: int | None = None
    first_goal_minute: int | None = None
    first_goal_player: str | None = None
    scoring_sequence: list[dict[str, Any]] = []
    goals: list[dict[str, Any]] = []
    if raw:
        id_to_side, id_to_name, side_to_id = build_participant_maps(raw)
        home_goals, away_goals = _scores_from_fixture(raw, id_to_side)
        goals = parse_uefa_goal_events(raw)
        if goals:
            first = goals[0]
            first_goal_minute = first.get("minute")
            first_goal_team_side = first.get("scoring_side")
            first_goal_player = first.get("player_name")
            pid = first.get("team_id")
            if pid is not None:
                try:
                    first_goal_team_id = int(pid)
                except (TypeError, ValueError):
                    first_goal_team_id = None
            if first_goal_team_side == "home":
                first_goal_team = home_team or id_to_name.get(side_to_id.get("home", 0), home_team)
            elif first_goal_team_side == "away":
                first_goal_team = away_team or id_to_name.get(side_to_id.get("away", 0), away_team)
            elif first_goal_team_side == "none":
                first_goal_team = None
            scoring_sequence = [
                {
                    "minute": g.get("minute"),
                    "scoring_side": g.get("scoring_side"),
                    "goal_kind": g.get("goal_kind"),
                    "team_id": g.get("team_id"),
                    "player_name": g.get("player_name"),
                }
                for g in goals
            ]
        if home_goals == 0 and away_goals == 0 and goals:
            home_goals, away_goals = _goals_tally_from_events(goals)
    total_goals = home_goals + away_goals
    if total_goals == 0:
        first_goal_team_side = "none"
    return {
        "home_goals": home_goals,
        "away_goals": away_goals,
        "first_goal_minute": first_goal_minute,
        "first_goal_team": first_goal_team,
        "first_goal_team_side": first_goal_team_side,
        "first_goal_team_id": first_goal_team_id,
        "first_goal_player": first_goal_player,
        "goal_events_count": len(goals),
        "scoring_sequence": scoring_sequence,
        "goal_count": len(goals),
    }


def build_provider_vector_fields(payload: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    fields.update(parse_uefa_xg(payload))
    fields.update(parse_uefa_pressure(payload))
    fields.update(parse_uefa_odds(payload))
    fields.update(parse_uefa_predictions(payload))
    fields.update(parse_uefa_lineups(payload))
    goals = parse_uefa_goal_events(payload)
    if goals:
        minutes = [g["minute"] for g in goals if g.get("minute") is not None]
        if minutes:
            fields["recent_first_goal_patterns"] = round(sum(minutes) / len(minutes), 2)
    coverage = {
        "xg": fields.get("home_xg") is not None,
        "pressure": fields.get("home_pressure") is not None,
        "odds": fields.get("implied_home") is not None,
        "predictions": fields.get("sportmonks_home_win") is not None,
        "lineups": fields.get("lineup_strength_home") is not None,
        "events": bool(goals),
        "statistics": bool(_fixture_data(payload) and (_fixture_data(payload) or {}).get("statistics")),
    }
    fields["coverage"] = coverage
    return fields
