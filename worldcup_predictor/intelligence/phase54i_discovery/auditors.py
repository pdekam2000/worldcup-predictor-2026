"""Audit Sportmonks fixture payloads for lineups, player stats, goalscorer odds."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_STARTER_TYPE = 11
_BENCH_TYPE = 12
_FINISHED = {5, 7, 8}

_GOALSCORER_MARKET_PATTERNS = (
    re.compile(r"goal\s*scor", re.I),
    re.compile(r"anytime", re.I),
    re.compile(r"first\s+goal", re.I),
    re.compile(r"last\s+goal", re.I),
    re.compile(r"player\s+to\s+score", re.I),
    re.compile(r"team\s+goalscorer", re.I),
    re.compile(r"team\s+to\s+score\s+first", re.I),
    re.compile(r"correct\s+score", re.I),
)

_PLAYER_STAT_DETAIL_NAMES = frozenset(
    {
        "minutes played",
        "goals",
        "assists",
        "shots",
        "shots on target",
        "shots on goal",
        "key passes",
        "yellowcards",
        "redcards",
        "rating",
        "expected goals",
        "xG",
        "xA",
    }
)


def _fixture_data(blob: dict[str, Any]) -> dict[str, Any]:
    data = (blob.get("payload") or {}).get("data")
    if isinstance(data, dict):
        return data
    payload = blob.get("payload")
    return payload if isinstance(payload, dict) else {}


def audit_lineups(data: dict[str, Any]) -> dict[str, Any]:
    lineups = [lu for lu in (data.get("lineups") or []) if isinstance(lu, dict)]
    starters = sum(1 for lu in lineups if int(lu.get("type_id") or 0) == _STARTER_TYPE)
    bench = sum(1 for lu in lineups if int(lu.get("type_id") or 0) == _BENCH_TYPE)
    positions = sum(1 for lu in lineups if lu.get("formation_position") is not None)
    formations = data.get("formations") or []
    formation_ok = isinstance(formations, list) and len(formations) >= 2
    sidelined = data.get("sidelined") or []
    sidelined_n = len(sidelined) if isinstance(sidelined, list) else 0
    subs = sum(
        1
        for ev in (data.get("events") or [])
        if isinstance(ev, dict) and "substitut" in str((ev.get("type") or {}).get("name") or "").lower()
    )
    captain_flags = 0
    for lu in lineups:
        for det in lu.get("details") or []:
            tname = str((det.get("type") or {}).get("name") or "").lower()
            if "captain" in tname:
                captain_flags += 1
    gk = sum(1 for lu in lineups if int(lu.get("formation_position") or 0) == 1)
    return {
        "lineup_rows": len(lineups),
        "starters": starters,
        "bench": bench,
        "has_starting_xi": starters >= 20,
        "has_bench": bench >= 5,
        "formation_positions": positions,
        "formations_available": formation_ok,
        "formation_strings": [f.get("formation") for f in formations if isinstance(f, dict)][:2],
        "captain_flags": captain_flags,
        "goalkeeper_slots": gk,
        "substitutions_in_events": subs,
        "sidelined_count": sidelined_n,
        "usable_prematch": starters >= 20 and formation_ok,
        "usable_historical_backtest": starters >= 20,
    }


def audit_player_stats(data: dict[str, Any]) -> dict[str, Any]:
    lineups = [lu for lu in (data.get("lineups") or []) if isinstance(lu, dict)]
    detail_hits: Counter[str] = Counter()
    players_with_minutes = 0
    players_with_goals = 0
    players_with_shots = 0
    players_with_xg = 0
    players_with_rating = 0
    for lu in lineups:
        had_minutes = had_goals = had_shots = had_xg = had_rating = False
        for det in lu.get("details") or []:
            if not isinstance(det, dict):
                continue
            tname = str((det.get("type") or {}).get("name") or "").strip()
            tl = tname.lower()
            if tl in _PLAYER_STAT_DETAIL_NAMES or any(x in tl for x in ("shot", "xg", "rating", "assist", "minute")):
                detail_hits[tname] += 1
            val = det.get("value") or det.get("data", {}).get("value")
            try:
                num = float(val) if val is not None else None
            except (TypeError, ValueError):
                num = None
            if "minute" in tl and num and num > 0:
                had_minutes = True
            if tl == "goals" and num and num > 0:
                had_goals = True
            if "shot" in tl:
                had_shots = True
            if "xg" in tl or "expected goal" in tl:
                had_xg = True
            if "rating" in tl:
                had_rating = True
        xg_lineup = lu.get("xGLineup") or lu.get("xgLineup") or []
        if isinstance(xg_lineup, list) and xg_lineup:
            had_xg = True
        if had_minutes:
            players_with_minutes += 1
        if had_goals:
            players_with_goals += 1
        if had_shots:
            players_with_shots += 1
        if had_xg:
            players_with_xg += 1
        if had_rating:
            players_with_rating += 1
    stats_block = data.get("statistics") or []
    team_stats = len(stats_block) if isinstance(stats_block, list) else 0
    return {
        "lineup_player_rows": len(lineups),
        "players_with_minutes": players_with_minutes,
        "players_with_goals": players_with_goals,
        "players_with_shots": players_with_shots,
        "players_with_xg": players_with_xg,
        "players_with_rating": players_with_rating,
        "team_statistics_types": team_stats,
        "detail_type_hits": dict(detail_hits.most_common(12)),
        "usable_goalscorer_engine": players_with_minutes >= 20 and (players_with_goals > 0 or players_with_shots > 0),
        "player_xg_available": players_with_xg > 0,
    }


def _market_name(entry: dict[str, Any]) -> str:
    return str((entry.get("market") or {}).get("name") or entry.get("market_description") or "").strip()


def audit_goalscorer_odds(data: dict[str, Any]) -> dict[str, Any]:
    odds = [o for o in (data.get("odds") or []) if isinstance(o, dict)]
    if not odds:
        return {
            "odds_rows": 0,
            "has_goalscorer_odds": False,
            "markets": {},
            "bookmakers": 0,
            "player_mapping_has_id": 0,
            "player_mapping_name_only": 0,
            "labels_by_market": {},
        }
    markets: Counter[str] = Counter()
    books: set[str] = set()
    gs_markets: Counter[str] = Counter()
    labels: dict[str, Counter[str]] = {}
    has_id = name_only = 0
    for o in odds:
        mname = _market_name(o)
        if mname:
            markets[mname] += 1
        bname = str((o.get("bookmaker") or {}).get("name") or "").strip()
        if bname:
            books.add(bname)
        is_gs = any(p.search(mname) for p in _GOALSCORER_MARKET_PATTERNS)
        if not is_gs:
            continue
        gs_markets[mname] += 1
        lbl = str(o.get("label") or "").strip()
        labels.setdefault(mname, Counter())[lbl] += 1
        if o.get("player_id"):
            has_id += 1
        elif o.get("name") or o.get("label"):
            name_only += 1
    return {
        "odds_rows": len(odds),
        "has_goalscorer_odds": sum(gs_markets.values()) > 0,
        "goalscorer_market_rows": sum(gs_markets.values()),
        "markets": dict(gs_markets),
        "all_market_count": len(markets),
        "bookmakers": len(books),
        "player_mapping_has_id": has_id,
        "player_mapping_name_only": name_only,
        "labels_by_market": {k: dict(v) for k, v in labels.items()},
        "has_first_anytime_last_labels": any(
            "First" in lbls or "Anytime" in lbls or "Last" in lbls for lbls in labels.values()
        ),
    }


def audit_fixture_blob(blob: dict[str, Any]) -> dict[str, Any]:
    data = _fixture_data(blob)
    if not data:
        return {"valid": False}
    state_id = int(data.get("state_id") or 0)
    return {
        "valid": True,
        "sportmonks_fixture_id": int(data.get("id") or blob.get("sportmonks_fixture_id") or 0),
        "league_id": int(data.get("league_id") or 0),
        "season_id": data.get("season_id"),
        "state_id": state_id,
        "finished": state_id in _FINISHED,
        "lineups": audit_lineups(data),
        "player_stats": audit_player_stats(data),
        "goalscorer_odds": audit_goalscorer_odds(data),
    }
