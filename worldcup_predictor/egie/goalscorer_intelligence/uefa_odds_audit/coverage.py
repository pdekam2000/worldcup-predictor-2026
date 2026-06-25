"""UEFA goalscorer odds coverage scan across Sportmonks cache."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.models import UEFA_LEAGUE_IDS, WC_LEAGUE_ID
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED
from worldcup_predictor.intelligence.phase54i_discovery.auditors import audit_goalscorer_odds

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_ALL_LEAGUES = {**UEFA_LEAGUE_IDS, WC_LEAGUE_ID: "world_cup"}


def scan_sportmonks_goalscorer_coverage() -> dict[str, Any]:
    """Scan cached Sportmonks payloads for strict + broad goalscorer market detection."""
    seen: set[int] = set()
    by_league: dict[int, dict[str, Any]] = {
        lid: {
            "league_id": lid,
            "league": name,
            "fixtures_in_cache": 0,
            "fixtures_strict_gs": set(),
            "fixtures_broad_gs": set(),
            "selection_count_strict": 0,
            "markets": Counter(),
            "bookmakers": Counter(),
        }
        for lid, name in _ALL_LEAGUES.items()
    }

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
            fid = int(data.get("id") or blob.get("sportmonks_fixture_id") or 0)
            if fid in seen:
                continue
            seen.add(fid)
            lid = int(data.get("league_id") or 0)
            if lid not in by_league:
                continue
            entry = by_league[lid]
            entry["fixtures_in_cache"] += 1
            finished = int(data.get("state_id") or 0) in _FINISHED
            strict = _extract_selections(data, finished=finished)
            broad = audit_goalscorer_odds(data)
            if strict:
                entry["fixtures_strict_gs"].add(fid)
                entry["selection_count_strict"] += len(strict)
                for r in strict:
                    entry["markets"][r.market] += 1
                    entry["bookmakers"][r.bookmaker] += 1
            if broad.get("has_goalscorer_odds"):
                entry["fixtures_broad_gs"].add(fid)

    out: dict[str, Any] = {"leagues": {}, "totals": {}}
    total_fixtures = total_gs = 0
    for lid, entry in by_league.items():
        fx = int(entry["fixtures_in_cache"])
        gs_strict = len(entry["fixtures_strict_gs"])
        gs_broad = len(entry["fixtures_broad_gs"])
        total_fixtures += fx
        total_gs += gs_strict
        out["leagues"][entry["league"]] = {
            "league_id": lid,
            "fixtures": fx,
            "fixtures_with_strict_goalscorer_odds": gs_strict,
            "fixtures_with_broad_goalscorer_odds": gs_broad,
            "coverage_pct_strict": round(gs_strict / fx, 4) if fx else 0.0,
            "coverage_pct_broad": round(gs_broad / fx, 4) if fx else 0.0,
            "selection_count": entry["selection_count_strict"],
            "market_count": len(entry["markets"]),
            "bookmaker_count": len(entry["bookmakers"]),
            "markets": dict(entry["markets"].most_common(10)),
            "bookmakers": dict(entry["bookmakers"].most_common(10)),
        }

    uefa_fx = sum(out["leagues"][n]["fixtures"] for n in UEFA_LEAGUE_IDS.values())
    uefa_gs = sum(out["leagues"][n]["fixtures_with_strict_goalscorer_odds"] for n in UEFA_LEAGUE_IDS.values())
    out["totals"] = {
        "uefa_fixtures_cached": uefa_fx,
        "uefa_fixtures_with_gs_odds": uefa_gs,
        "uefa_coverage_pct": round(uefa_gs / uefa_fx, 4) if uefa_fx else 0.0,
        "wc_fixtures_cached": out["leagues"]["world_cup"]["fixtures"],
        "wc_fixtures_with_gs_odds_cache": out["leagues"]["world_cup"]["fixtures_with_strict_goalscorer_odds"],
    }
    return out


def scan_dataset_v3_coverage(df) -> dict[str, Any]:
    """Coverage in intelligence dataset v3 (API-Football WC bridge overlay)."""
    from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import LEAGUE_LABELS

    rows: dict[str, Any] = {}
    for lid, grp in df.groupby("league_id"):
        label = LEAGUE_LABELS.get(int(lid), f"league_{lid}")
        fx = int(grp["sportmonks_fixture_id"].nunique())
        if "has_goalscorer_odds" in grp.columns:
            with_odds = int(grp.loc[grp["has_goalscorer_odds"] == 1, "sportmonks_fixture_id"].nunique())
        else:
            with_odds = int(grp.loc[grp["odds_implied_anytime"].notna(), "sportmonks_fixture_id"].nunique())
        rows[label] = {
            "fixtures": fx,
            "fixtures_with_goalscorer_odds": with_odds,
            "coverage_pct": round(with_odds / fx, 4) if fx else 0.0,
        }
    uefa_fx = sum(rows[n]["fixtures"] for n in UEFA_LEAGUE_IDS.values() if n in rows)
    uefa_odds = sum(rows[n]["fixtures_with_goalscorer_odds"] for n in UEFA_LEAGUE_IDS.values() if n in rows)
    return {
        "by_league": rows,
        "uefa_fixtures": uefa_fx,
        "uefa_with_odds": uefa_odds,
        "uefa_coverage_pct": round(uefa_odds / uefa_fx, 4) if uefa_fx else 0.0,
    }
