"""Load Sportmonks UEFA goalscorer odds and build expansion bridges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_bridge.fixture_mapper import build_fixture_bridges
from worldcup_predictor.egie.goalscorer_bridge.models import FixtureBridge
from worldcup_predictor.egie.goalscorer_bridge.odds_loader import load_all_bridged_odds
from worldcup_predictor.egie.goalscorer_bridge.player_mapper import load_lineup_df_for_fixtures, map_bridged_odds
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED
from worldcup_predictor.egie.goalscorer_odds_mapping.models import MappedOddsSelection, RawOddsSelection
from worldcup_predictor.egie.goalscorer_uefa_expansion.models import UEFA_LEAGUE_IDS

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)


def _label_from_market(market: str) -> str:
    low = market.lower()
    if "first" in low:
        return "First"
    if "last" in low:
        return "Last"
    return "Anytime"


def load_sportmonks_uefa_odds(fixture_ids: set[int] | None = None) -> list[RawOddsSelection]:
    """Load strict player goalscorer odds from Sportmonks UEFA cache."""
    rows: list[RawOddsSelection] = []
    seen: set[int] = set()

    for root in _CACHE_ROOTS:
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
            fid = int(data.get("id") or 0)
            if fid in seen:
                continue
            seen.add(fid)
            lid = int(data.get("league_id") or 0)
            if lid not in UEFA_LEAGUE_IDS:
                continue
            if fixture_ids is not None and fid not in fixture_ids:
                continue
            finished = int(data.get("state_id") or 0) in _FINISHED
            for r in _extract_selections(data, finished=finished):
                rows.append(r)
    return rows


def build_uefa_identity_bridges(fixture_ids: list[int]) -> list[FixtureBridge]:
    """Direct Sportmonks identity bridges for UEFA fixtures with odds."""
    bridges: list[FixtureBridge] = []
    id_set = set(fixture_ids)
    seen: set[int] = set()

    for root in _CACHE_ROOTS:
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
            fid = int(data.get("id") or 0)
            if fid not in id_set or fid in seen:
                continue
            seen.add(fid)
            home = away = None
            home_id = away_id = None
            for p in data.get("participants") or []:
                loc = str((p.get("meta") or {}).get("location") or "").lower()
                if loc == "home":
                    home, home_id = str(p.get("name") or ""), p.get("id")
                elif loc == "away":
                    away, away_id = str(p.get("name") or ""), p.get("id")
            bridges.append(
                FixtureBridge(
                    api_football_fixture_id=fid,
                    internal_fixture_id=fid,
                    sportmonks_fixture_id=fid,
                    home_team=home or "",
                    away_team=away or "",
                    home_team_id=int(home_id) if home_id else None,
                    away_team_id=int(away_id) if away_id else None,
                    league=UEFA_LEAGUE_IDS.get(int(data.get("league_id") or 0), "uefa"),
                    season=int(data.get("season_id") or 0) or None,
                    match_date=str(data.get("starting_at") or "")[:10] or None,
                    status="finished" if int(data.get("state_id") or 0) in _FINISHED else "scheduled",
                    bridge_confidence="HIGH",
                    bridge_method="sportmonks_identity",
                    sportmonks_lineups_available=len(data.get("lineups") or []) >= 20,
                    notes="uefa_sportmonks_direct",
                )
            )
    return bridges


def build_expanded_bridge_set() -> tuple[list[FixtureBridge], list[RawOddsSelection], dict[str, Any]]:
    """Merge 54O WC bridges with UEFA Sportmonks direct bridges."""
    wc_bridges = build_fixture_bridges()
    wc_mapped = {int(b.sportmonks_fixture_id) for b in wc_bridges if b.sportmonks_fixture_id}

    uefa_raw = load_sportmonks_uefa_odds()
    uefa_fixture_ids = sorted({r.sportmonks_fixture_id for r in uefa_raw})
    uefa_bridges = build_uefa_identity_bridges(uefa_fixture_ids)

    merged_bridges: list[FixtureBridge] = []
    seen_sm: set[int] = set()
    for b in wc_bridges:
        if b.sportmonks_fixture_id and int(b.sportmonks_fixture_id) not in seen_sm:
            merged_bridges.append(b)
            seen_sm.add(int(b.sportmonks_fixture_id))
    for b in uefa_bridges:
        sm = int(b.sportmonks_fixture_id or 0)
        if sm and sm not in seen_sm:
            merged_bridges.append(b)
            seen_sm.add(sm)

    wc_odds = load_all_bridged_odds(wc_bridges)
    all_odds = wc_odds + uefa_raw

    meta = {
        "wc_bridges": len(wc_bridges),
        "wc_bridges_mapped": len(wc_mapped),
        "uefa_bridges": len(uefa_bridges),
        "merged_bridges": len(merged_bridges),
        "wc_odds_selections": len(wc_odds),
        "uefa_odds_selections": len(uefa_raw),
        "total_odds_selections": len(all_odds),
        "uefa_fixture_ids": uefa_fixture_ids,
    }
    return merged_bridges, all_odds, meta


def map_expanded_odds(
    bridges: list[FixtureBridge],
    raw_odds: list[RawOddsSelection],
) -> tuple[list[MappedOddsSelection], list[dict[str, Any]], dict[str, Any]]:
    """Reuse 54O player mapper on expanded bridge set."""
    sm_ids = sorted({int(b.sportmonks_fixture_id) for b in bridges if b.sportmonks_fixture_id})
    lineup_df = load_lineup_df_for_fixtures(sm_ids)
    mapped, unmapped, summary, diagnostics = map_bridged_odds(raw_odds, lineup_df, bridges)
    return mapped, unmapped, {"summary": summary.to_dict() if hasattr(summary, "to_dict") else summary, "diagnostics": diagnostics}
