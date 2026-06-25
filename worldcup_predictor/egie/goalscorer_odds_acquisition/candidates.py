"""Identify fixtures with goalscorer odds and backfill candidates."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.models import PRIORITY_LEAGUES, CandidateFixture
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED
from worldcup_predictor.egie.goalscorer_odds_acquisition.inventory import (
    DB_PATH,
    ROOT,
    _scan_api_football_payload,
)
from worldcup_predictor.intelligence.phase54i_discovery.auditors import audit_fixture_blob

_SPORTMONKS_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)


def _priority_score(*, league_id: int | None, competition_key: str | None, has_gs: bool, odds_rows: int) -> int:
    score = 0
    if league_id in PRIORITY_LEAGUES:
        score += 100 - list(PRIORITY_LEAGUES.keys()).index(league_id)
    if competition_key:
        ck = competition_key.lower()
        if "world_cup" in ck:
            score += 120
        elif "champions" in ck:
            score += 90
        elif "europa" in ck:
            score += 80
        elif "conference" in ck:
            score += 70
    if has_gs:
        score += 50
    if odds_rows > 100:
        score += 20
    elif odds_rows > 50:
        score += 10
    return score


def _league_label(league_id: int | None, competition_key: str | None = None) -> str:
    if competition_key:
        return competition_key
    if league_id in PRIORITY_LEAGUES:
        return PRIORITY_LEAGUES[league_id]
    return f"league_{league_id or 'unknown'}"


def identify_api_football_candidates() -> list[CandidateFixture]:
    if not DB_PATH.is_file():
        return []

    conn = sqlite3.connect(DB_PATH)
    seen: set[int] = set()
    out: list[CandidateFixture] = []

    for row in conn.execute(
        """
        SELECT o.fixture_id, o.payload_json, f.competition_key, f.season, f.kickoff_utc
        FROM odds_snapshots o
        LEFT JOIN fixtures f ON f.fixture_id = o.fixture_id
        """
    ).fetchall():
        fid = int(row[0])
        if fid in seen:
            continue
        seen.add(fid)
        try:
            payload = json.loads(row[1])
        except json.JSONDecodeError:
            continue
        gs_rows, markets, books = _scan_api_football_payload(payload, fixture_id=fid)
        if not gs_rows:
            continue
        book = next(iter(books)) if books else "mixed"
        if len(books) > 1:
            book = f"mixed({len(books)})"
        comp = row[2]
        season = row[3]
        kickoff = row[4]
        out.append(
            CandidateFixture(
                fixture_id=fid,
                source="api_football_odds_snapshots",
                league=_league_label(None, comp),
                season=season,
                date=str(kickoff)[:10] if kickoff else None,
                bookmaker=book,
                market_count=len(markets),
                selection_count=len(gs_rows),
                priority_score=_priority_score(league_id=None, competition_key=comp, has_gs=True, odds_rows=len(gs_rows)),
                has_lineups=False,
                finished=True,
                notes="Already in SQLite odds_snapshots",
            )
        )
    conn.close()
    return sorted(out, key=lambda c: (-c.priority_score, c.date or ""))


def identify_sportmonks_with_goalscorer() -> list[CandidateFixture]:
    out: list[CandidateFixture] = []
    seen: set[int] = set()

    for root in _SPORTMONKS_CACHE_ROOTS:
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
            finished = int(data.get("state_id") or 0) in _FINISHED
            gs = _extract_selections(data, finished=finished)
            if not gs:
                continue
            seen.add(fid)
            league_id = int(data.get("league_id") or 0) or None
            books = {s.bookmaker for s in gs}
            markets = {s.market for s in gs}
            lu = audit_fixture_blob(blob).get("lineups") or {}
            out.append(
                CandidateFixture(
                    fixture_id=fid,
                    source="sportmonks_cache",
                    league=_league_label(league_id),
                    season=data.get("season_id"),
                    date=str(data.get("starting_at") or "")[:10] or None,
                    bookmaker=books.pop() if len(books) == 1 else f"mixed({len(books)})",
                    market_count=len(markets),
                    selection_count=len(gs),
                    priority_score=_priority_score(league_id=league_id, competition_key=None, has_gs=True, odds_rows=len(gs)),
                    has_lineups=bool(lu.get("has_starting_xi")),
                    finished=finished,
                    notes=str(path),
                )
            )
    return sorted(out, key=lambda c: (-c.priority_score, c.date or ""))


def identify_sportmonks_backfill_candidates(*, min_odds_rows: int = 50) -> list[CandidateFixture]:
    """UEFA/xG cache fixtures with odds but no goalscorer markets — Sportmonks re-fetch candidates."""
    have_gs = {c.fixture_id for c in identify_sportmonks_with_goalscorer()}
    out: list[CandidateFixture] = []
    seen: set[int] = set()

    for root in _SPORTMONKS_CACHE_ROOTS:
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
            if fid in seen or fid in have_gs:
                continue
            seen.add(fid)
            odds_n = len(data.get("odds") or [])
            if odds_n < min_odds_rows:
                continue
            finished = int(data.get("state_id") or 0) in _FINISHED
            if not finished:
                continue
            league_id = int(data.get("league_id") or 0) or None
            if league_id not in PRIORITY_LEAGUES:
                continue
            lu = audit_fixture_blob(blob).get("lineups") or {}
            out.append(
                CandidateFixture(
                    fixture_id=fid,
                    source="sportmonks_backfill_candidate",
                    league=_league_label(league_id),
                    season=data.get("season_id"),
                    date=str(data.get("starting_at") or "")[:10] or None,
                    bookmaker="unknown",
                    market_count=0,
                    selection_count=0,
                    priority_score=_priority_score(league_id=league_id, competition_key=None, has_gs=False, odds_rows=odds_n),
                    has_lineups=bool(lu.get("has_starting_xi")),
                    finished=True,
                    notes=f"odds_rows={odds_n}; no GS in cache",
                )
            )
    return sorted(out, key=lambda c: (-c.priority_score, c.date or ""), reverse=False)


def build_candidate_lists() -> dict[str, Any]:
    with_gs_api = identify_api_football_candidates()
    with_gs_sm = identify_sportmonks_with_goalscorer()
    backfill = identify_sportmonks_backfill_candidates()

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "with_goalscorer_odds": {
            "api_football": [c.to_dict() for c in with_gs_api],
            "sportmonks": [c.to_dict() for c in with_gs_sm],
        },
        "backfill_candidates": [c.to_dict() for c in backfill],
        "counts": {
            "api_football_with_gs": len(with_gs_api),
            "sportmonks_with_gs": len(with_gs_sm),
            "sportmonks_backfill_candidates": len(backfill),
            "total_with_gs_union": len(with_gs_api) + len(with_gs_sm),
        },
    }
