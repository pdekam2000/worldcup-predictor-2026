"""Extract goalscorer odds from cached Sportmonks payloads."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_mapping.models import MappingSummary, RawOddsSelection

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_FINISHED = {5, 7, 8}

_GOALSCORER_PATTERNS = (
    re.compile(r"goal\s*scor", re.I),
    re.compile(r"player\s+to\s+score", re.I),
    re.compile(r"team\s+goalscorer", re.I),
)


def _is_goalscorer_market(name: str) -> bool:
    return any(p.search(name) for p in _GOALSCORER_PATTERNS)


def _market_name(entry: dict[str, Any]) -> str:
    return str((entry.get("market") or {}).get("name") or entry.get("market_description") or "").strip()


def _goalscorer_market_label(entry: dict[str, Any]) -> str | None:
    mname = _market_name(entry)
    mdesc = str(entry.get("market_description") or "").strip()
    if _is_goalscorer_market(mdesc):
        return mdesc
    if _is_goalscorer_market(mname):
        return mname
    return None


def _extract_selections(data: dict[str, Any], *, finished: bool) -> list[RawOddsSelection]:
    fid = int(data.get("id") or 0)
    league_id = int(data.get("league_id") or 0) or None
    season_id = int(data.get("season_id") or 0) or None
    rows: list[RawOddsSelection] = []
    for o in data.get("odds") or []:
        if not isinstance(o, dict):
            continue
        market = _goalscorer_market_label(o)
        if not market:
            continue
        selection = str(o.get("name") or "").strip()
        if not selection:
            continue
        try:
            odds = float(o.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if odds <= 1.0:
            continue
        book = str((o.get("bookmaker") or {}).get("name") or "unknown")
        label = str(o.get("label") or "")
        ts = o.get("latest_bookmaker_update") or o.get("created_at")
        rows.append(
            RawOddsSelection(
                sportmonks_fixture_id=fid,
                bookmaker=book,
                market=market,
                label=label,
                selection_name=selection,
                odds=round(odds, 4),
                implied_probability=round(1.0 / odds, 6),
                timestamp=str(ts) if ts else None,
                finished=finished,
                league_id=league_id,
                season_id=season_id,
            )
        )
    return rows


def scan_cache_odds() -> tuple[list[RawOddsSelection], MappingSummary]:
    fixture_payloads: dict[int, tuple[dict[str, Any], bool, Path]] = {}

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
            fid = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
            finished = int(data.get("state_id") or 0) in _FINISHED
            selections = _extract_selections(data, finished=finished)
            prev = fixture_payloads.get(fid)
            if prev is None or len(selections) > len(_extract_selections(prev[0], finished=prev[1])):
                fixture_payloads[fid] = (data, finished, path)

    all_rows: list[RawOddsSelection] = []
    fixtures_with_odds: set[int] = set()
    books: set[str] = set()
    markets: set[str] = set()
    historical = upcoming = 0

    for fid, (data, finished, _path) in fixture_payloads.items():
        selections = _extract_selections(data, finished=finished)
        if selections:
            fixtures_with_odds.add(fid)
            all_rows.extend(selections)
            if finished:
                historical += 1
            else:
                upcoming += 1
            for s in selections:
                books.add(s.bookmaker)
                markets.add(s.market)

    summary = MappingSummary(
        fixtures_audited=len(fixture_payloads),
        fixtures_with_goalscorer_odds=len(fixtures_with_odds),
        bookmaker_count=len(books),
        market_count=len(markets),
        selection_count=len(all_rows),
        historical_fixtures=historical,
        upcoming_fixtures=upcoming,
    )
    return all_rows, summary


def audit_report(raw_rows: list[RawOddsSelection], summary: MappingSummary) -> dict[str, Any]:
    by_market = Counter(r.market for r in raw_rows)
    by_label = Counter((r.market, r.label) for r in raw_rows)
    by_book = Counter(r.bookmaker for r in raw_rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary.to_dict(),
        "markets": dict(by_market.most_common(20)),
        "labels": {f"{m}|{l}": c for (m, l), c in by_label.most_common(30)},
        "bookmakers": dict(by_book.most_common(20)),
        "sample_selections": [r.to_dict() for r in raw_rows[:5]],
    }
