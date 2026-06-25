"""Collect normalized MBI odds selections from all sources."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.market_classifier import classify_market, is_goalscorer_market_text
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import normalize_snapshot_odds_lines
from worldcup_predictor.egie.uefa_club.odds_intelligence import _float, _market_key, _side_from_label
from worldcup_predictor.mbi.models import OddsSelection, assign_odds_bucket
from worldcup_predictor.mbi.outcomes import enrich_sportmonks_outcomes_from_cache, load_outcome_maps, resolve_hit

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "football_intelligence.db"

_SPORTMONKS_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_API_MW = re.compile(r"match winner|1x2|match result|home/draw/away", re.I)
_API_FTS = re.compile(r"first team to score|team to score first|first goal", re.I)
_API_OU = re.compile(r"goals over/under|goal line|total goals", re.I)
_API_GS_ANY = re.compile(r"anytime|goalscorers?|player to score", re.I)
_API_GS_FIRST = re.compile(r"first goalscorer|first goal scorer", re.I)

_ODDALERTS_MARKET_MAP = {
    "ft_result": "match_winner",
    "ht_result": "match_winner",
    "total_goals": "over_under",
    "goal_line": "over_under",
    "btts": "over_under",
    "btts_o25": "over_under",
}


def _implied(odds: float) -> float:
    return round(1.0 / odds, 6) if odds > 1.0 else 0.0


def _api_market_key(name: str) -> str | None:
    if _API_MW.search(name):
        return "match_winner"
    if _API_FTS.search(name) and "correct score" not in name.lower():
        return "first_team_to_score"
    if _API_GS_FIRST.search(name):
        return "first_goalscorer"
    if _API_GS_ANY.search(name):
        return "anytime_goalscorer"
    if _API_OU.search(name):
        return "over_under"
    return None


def _normalize_api_selection(market_key: str, selection: str) -> str | None:
    sel = selection.lower().strip()
    if market_key == "match_winner":
        return {"home": "home", "away": "away", "draw": "draw", "1": "home", "2": "away", "x": "draw"}.get(sel, sel)
    if market_key == "first_team_to_score":
        return {"home": "home", "away": "away", "no goal": "none"}.get(sel, sel)
    if market_key == "over_under":
        if "over 2.5" in sel or sel == "over":
            return "over_2_5"
        if "under 2.5" in sel or sel == "under":
            return "under_2_5"
        if sel in ("yes", "no") and market_key == "over_under":
            return "over_2_5" if sel == "yes" else "under_2_5"
    if market_key in ("anytime_goalscorer", "first_goalscorer"):
        return selection.strip()
    return selection.strip()


def _collect_sportmonks(outcomes: dict[str, Any]) -> list[OddsSelection]:
    rows: list[OddsSelection] = []
    seen: set[int] = set()

    for root in _SPORTMONKS_ROOTS:
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
            if not fid or fid in seen:
                continue
            seen.add(fid)
            fixture_key = str(fid)
            enrich_sportmonks_outcomes_from_cache(blob, fixture_key, outcomes)
            league = str(data.get("league_id") or "")
            season = int(data.get("season_id") or 0) or None

            for entry in data.get("odds") or []:
                if not isinstance(entry, dict):
                    continue
                mname = str((entry.get("market") or {}).get("name") or entry.get("market_description") or "")
                mkey = _market_key(mname)
                label = str(entry.get("label") or entry.get("name") or "")
                dec = _float(entry.get("value") or entry.get("dp3") or entry.get("odd"))
                if dec is None or dec < 1.10:
                    continue
                book = str((entry.get("bookmaker") or {}).get("name") or "unknown")

                if mkey == "match_winner":
                    side = _side_from_label(label)
                    if side not in ("home", "draw", "away"):
                        continue
                    sel_key = side
                    market_key = "match_winner"
                elif mkey == "first_team_to_score":
                    side = _side_from_label(label)
                    if side not in ("home", "away"):
                        continue
                    sel_key = side
                    market_key = "first_team_to_score"
                elif mkey == "over_under":
                    total = str(entry.get("total") or entry.get("name") or label or "")
                    if "2.5" not in total and "2.5" not in label:
                        continue
                    side = _side_from_label(label)
                    if side == "yes":
                        sel_key = "over_2_5"
                    elif side == "no":
                        sel_key = "under_2_5"
                    else:
                        continue
                    market_key = "over_under"
                elif is_goalscorer_market_text(mname):
                    kind = classify_market(mname)
                    if kind not in ("player_goalscorer", "player_goalscorer_team_scoped"):
                        continue
                    sel_name = str(entry.get("name") or label).strip()
                    if not sel_name:
                        continue
                    market_key = "first_goalscorer" if re.search(r"first", mname, re.I) else "anytime_goalscorer"
                    sel_key = sel_name.lower()
                else:
                    continue

                bucket = assign_odds_bucket(dec)
                if not bucket:
                    continue
                hit, outcome = resolve_hit(
                    market_key=market_key,
                    selection=sel_key,
                    fixture_key=fixture_key,
                    source="sportmonks_cache",
                    outcomes=outcomes,
                )
                rows.append(
                    OddsSelection(
                        source="sportmonks_cache",
                        fixture_key=fixture_key,
                        market_key=market_key,
                        selection=sel_key,
                        odds=round(dec, 4),
                        bookmaker=book,
                        league=league,
                        season=season,
                        implied_probability=_implied(dec),
                        bucket=bucket,
                        hit=hit,
                        outcome_label=outcome,
                    )
                )

            for raw in _extract_selections(data, finished=int(data.get("state_id") or 0) in _FINISHED):
                mname = raw.market
                if not is_goalscorer_market_text(mname):
                    continue
                market_key = "first_goalscorer" if re.search(r"first", mname, re.I) else "anytime_goalscorer"
                sel_key = raw.selection_name.strip().lower()
                dec = raw.odds
                bucket = assign_odds_bucket(dec)
                if not bucket:
                    continue
                hit, outcome = resolve_hit(
                    market_key=market_key,
                    selection=sel_key,
                    fixture_key=fixture_key,
                    source="sportmonks_cache",
                    outcomes=outcomes,
                )
                rows.append(
                    OddsSelection(
                        source="sportmonks_cache",
                        fixture_key=fixture_key,
                        market_key=market_key,
                        selection=sel_key,
                        odds=dec,
                        bookmaker=raw.bookmaker,
                        league=league,
                        season=season,
                        implied_probability=_implied(dec),
                        bucket=bucket,
                        hit=hit,
                        outcome_label=outcome,
                    )
                )
    return rows


def _collect_api_snapshots(outcomes: dict[str, Any]) -> list[OddsSelection]:
    if not DB_PATH.is_file():
        return []
    rows: list[OddsSelection] = []
    conn = sqlite3.connect(DB_PATH)
    seen: set[int] = set()
    for fid, payload_json, comp_key in conn.execute(
        "SELECT fixture_id, payload_json, competition_key FROM odds_snapshots"
    ):
        if fid in seen:
            continue
        seen.add(fid)
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        fixture_key = str(int(fid))
        lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fid))
        for line in lines:
            market_key = _api_market_key(line.market_name)
            if not market_key:
                continue
            sel_key = _normalize_api_selection(market_key, line.selection)
            if not sel_key:
                continue
            if market_key == "over_under" and "2.5" not in line.selection.lower() and market_key == "over_under":
                if line.selection.lower() not in ("over", "under", "yes", "no"):
                    continue
            dec = line.odd
            bucket = assign_odds_bucket(dec)
            if not bucket:
                continue
            hit, outcome = resolve_hit(
                market_key=market_key,
                selection=sel_key if market_key not in ("anytime_goalscorer", "first_goalscorer") else sel_key.lower(),
                fixture_key=fixture_key,
                source="odds_snapshots",
                outcomes=outcomes,
            )
            rows.append(
                OddsSelection(
                    source="odds_snapshots",
                    fixture_key=fixture_key,
                    market_key=market_key,
                    selection=sel_key,
                    odds=round(dec, 4),
                    bookmaker=line.bookmaker,
                    league=str(comp_key or ""),
                    season=None,
                    implied_probability=_implied(dec),
                    bucket=bucket,
                    hit=hit,
                    outcome_label=outcome,
                )
            )
    conn.close()
    return rows


def _collect_oddalerts(outcomes: dict[str, Any]) -> list[OddsSelection]:
    if not DB_PATH.is_file():
        return []
    rows: list[OddsSelection] = []
    conn = sqlite3.connect(DB_PATH)
    for (
        oa_fid,
        internal_fid,
        league,
        season,
        bookmaker,
        market,
        selection,
        closing_odds,
    ) in conn.execute(
        """
        SELECT oddalerts_fixture_id, internal_fixture_id, league, season,
               bookmaker, market, selection, closing_odds
        FROM oddalerts_odds_history
        WHERE closing_odds IS NOT NULL AND closing_odds >= 1.10
        """
    ):
        market_key = _ODDALERTS_MARKET_MAP.get(str(market))
        if not market_key:
            continue
        fixture_key = str(internal_fid or oa_fid)
        sel = str(selection).lower().strip()
        if market_key == "match_winner":
            sel_key = {"home": "home", "away": "away", "draw": "draw"}.get(sel, sel)
        elif market_key == "over_under":
            if market == "btts":
                sel_key = "over_2_5" if sel == "yes" else "under_2_5"
            elif "over" in sel:
                sel_key = "over_2_5"
            elif "under" in sel:
                sel_key = "under_2_5"
            else:
                sel_key = sel
        else:
            sel_key = sel
        dec = float(closing_odds)
        bucket = assign_odds_bucket(dec)
        if not bucket:
            continue
        hit, outcome = resolve_hit(
            market_key=market_key,
            selection=sel_key,
            fixture_key=fixture_key,
            source="oddalerts",
            outcomes=outcomes,
        )
        rows.append(
            OddsSelection(
                source="oddalerts",
                fixture_key=fixture_key,
                market_key=market_key,
                selection=sel_key,
                odds=round(dec, 4),
                bookmaker=str(bookmaker),
                league=str(league),
                season=int(season) if season else None,
                implied_probability=_implied(dec),
                bucket=bucket,
                hit=hit,
                outcome_label=outcome,
            )
        )
    conn.close()
    return rows


def collect_all_selections() -> tuple[list[OddsSelection], dict[str, Any]]:
    outcomes = load_outcome_maps()
    sportmonks = _collect_sportmonks(outcomes)
    api = _collect_api_snapshots(outcomes)
    oddalerts = _collect_oddalerts(outcomes)
    all_rows = sportmonks + api + oddalerts
    meta = {
        "sportmonks_selections": len(sportmonks),
        "api_snapshot_selections": len(api),
        "oddalerts_selections": len(oddalerts),
        "total_selections": len(all_rows),
        "with_outcomes": sum(1 for r in all_rows if r.hit is not None),
        "outcome_fixtures_api": len(outcomes["by_api_fixture"]),
        "outcome_fixtures_sportmonks": len(outcomes["by_sportmonks_fixture"]),
    }
    return all_rows, meta
