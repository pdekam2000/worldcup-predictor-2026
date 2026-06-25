"""UEFA goalscorer odds inventory — Part A & B."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.inventory import (
    DB_PATH,
    _scan_api_football_payload,
    build_inventory,
)
from worldcup_predictor.egie.goalscorer_odds_acquisition.market_classifier import classify_market
from worldcup_predictor.egie.goalscorer_uefa_expansion.models import MARKET_TYPES, UEFA_LEAGUE_IDS, WC_LEAGUE_ID
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED, scan_cache_odds
from worldcup_predictor.intelligence.phase54i_discovery.auditors import audit_goalscorer_odds

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_ALL_LEAGUES = {**UEFA_LEAGUE_IDS, WC_LEAGUE_ID: "world_cup"}


def _classify_market_type(market: str) -> str:
    low = (market or "").lower()
    if "last" in low and "scor" in low:
        return "last_goalscorer"
    if "first" in low and "scor" in low:
        return "first_goalscorer"
    if "team" in low and "scor" in low:
        return "team_goalscorer"
    if "player to score" in low or "to score" in low:
        return "player_to_score"
    if "anytime" in low or low == "goalscorers" or "goal scorer" in low:
        return "anytime_goalscorer"
    return "other"


def audit_all_sources() -> dict[str, Any]:
    """Part A — audit odds_snapshots, cache, API-Football, Sportmonks."""
    consolidated = build_inventory()

    sm_rows, sm_summary = scan_cache_odds()
    market_type_counts: Counter[str] = Counter()
    for r in sm_rows:
        market_type_counts[_classify_market_type(r.market)] += 1

    api_gs_by_comp: Counter[str] = Counter()
    if DB_PATH.is_file():
        conn = sqlite3.connect(DB_PATH)
        seen: set[int] = set()
        for fid, payload_json, comp in conn.execute(
            """
            SELECT o.fixture_id, o.payload_json, COALESCE(f.competition_key, 'unknown')
            FROM odds_snapshots o
            LEFT JOIN fixtures f ON f.fixture_id = o.fixture_id
            """
        ):
            if fid in seen:
                continue
            seen.add(fid)
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
            rows, _, _ = _scan_api_football_payload(payload, fixture_id=int(fid))
            if rows:
                api_gs_by_comp[str(comp)] += 1
        conn.close()

    return {
        "consolidated_inventory": consolidated,
        "sportmonks_strict_summary": sm_summary.to_dict() if hasattr(sm_summary, "to_dict") else {},
        "sportmonks_strict_selections": len(sm_rows),
        "market_type_counts_strict": dict(market_type_counts),
        "api_football_gs_by_competition": dict(api_gs_by_comp),
        "sources_audited": [s.get("source") for s in consolidated.get("sources", [])],
    }


def build_uefa_inventory() -> dict[str, Any]:
    """Part B — UEFA coverage by league, season, bookmaker, market type."""
    seen: set[int] = set()
    by_league: dict[str, dict[str, Any]] = {}
    by_season: Counter[int] = Counter()
    by_bookmaker: Counter[str] = Counter()
    by_market_type: Counter[str] = Counter()
    by_market_name: Counter[str] = Counter()
    fixture_records: list[dict[str, Any]] = []

    for root in _CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            fid = int(data.get("id") or 0)
            if fid in seen:
                continue
            seen.add(fid)
            lid = int(data.get("league_id") or 0)
            if lid not in UEFA_LEAGUE_IDS:
                continue
            league = UEFA_LEAGUE_IDS[lid]
            season_id = int(data.get("season_id") or 0)
            finished = int(data.get("state_id") or 0) in _FINISHED
            strict = _extract_selections(data, finished=finished)
            broad = audit_goalscorer_odds(data)

            entry = by_league.setdefault(
                league,
                {
                    "league_id": lid,
                    "fixtures_in_cache": 0,
                    "fixtures_strict_player_gs": 0,
                    "fixtures_broad_gs": 0,
                    "selection_count": 0,
                    "fixture_ids_strict": [],
                },
            )
            entry["fixtures_in_cache"] += 1

            if broad.get("has_goalscorer_odds"):
                entry["fixtures_broad_gs"] += 1

            if strict:
                entry["fixtures_strict_player_gs"] += 1
                entry["selection_count"] += len(strict)
                entry["fixture_ids_strict"].append(fid)
                by_season[season_id] += 1
                for r in strict:
                    by_bookmaker[r.bookmaker] += 1
                    by_market_name[r.market] += 1
                    by_market_type[_classify_market_type(r.market)] += 1
                fixture_records.append(
                    {
                        "sportmonks_fixture_id": fid,
                        "league": league,
                        "season_id": season_id,
                        "selection_count": len(strict),
                        "bookmakers": list({r.bookmaker for r in strict}),
                        "markets": list({r.market for r in strict}),
                    }
                )

    uefa_fixtures = sum(e["fixtures_in_cache"] for e in by_league.values())
    uefa_strict = sum(e["fixtures_strict_player_gs"] for e in by_league.values())
    coverage_pct = uefa_strict / uefa_fixtures if uefa_fixtures else 0.0

    return {
        "by_league": {
            k: {
                **v,
                "coverage_pct_strict": round(v["fixtures_strict_player_gs"] / v["fixtures_in_cache"], 4)
                if v["fixtures_in_cache"]
                else 0.0,
                "fixture_ids_strict": v["fixture_ids_strict"],
            }
            for k, v in by_league.items()
        },
        "by_season": dict(by_season),
        "by_bookmaker": dict(by_bookmaker.most_common(20)),
        "by_market_type": dict(by_market_type),
        "by_market_name": dict(by_market_name.most_common(20)),
        "fixture_records": fixture_records,
        "totals": {
            "uefa_fixtures_cached": uefa_fixtures,
            "uefa_fixtures_strict_player_gs": uefa_strict,
            "uefa_coverage_pct_strict": round(coverage_pct, 4),
            "selection_count": sum(by_market_name.values()),
        },
    }
