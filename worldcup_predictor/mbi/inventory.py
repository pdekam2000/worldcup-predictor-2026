"""Part A — audit all available odds snapshots."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED, scan_cache_odds
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import normalize_snapshot_odds_lines
from worldcup_predictor.mbi.models import InventorySummary

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "football_intelligence.db"

_SPORTMONKS_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _scan_sportmonks_cache() -> dict[str, Any]:
    fixtures = 0
    odds_rows = 0
    markets: Counter[str] = Counter()
    books: Counter[str] = Counter()
    leagues: Counter[str] = Counter()
    seasons: Counter[str] = Counter()
    seen: set[int] = set()

    for root in _SPORTMONKS_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            blob = _load_json(path)
            if not isinstance(blob, dict):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            fid = int(data.get("id") or 0)
            if not fid or fid in seen:
                continue
            seen.add(fid)
            fixtures += 1
            league_id = data.get("league_id")
            season_id = data.get("season_id")
            if league_id:
                leagues[str(league_id)] += 1
            if season_id:
                seasons[str(season_id)] += 1
            state = int((data.get("state_id") or 0))
            finished = state in _FINISHED
            for row in _extract_selections(data, finished=finished):
                odds_rows += 1
                markets[row.market] += 1
                books[row.bookmaker] += 1
            for o in data.get("odds") or []:
                if not isinstance(o, dict):
                    continue
                mname = str((o.get("market") or {}).get("name") or o.get("market_description") or "")
                if mname:
                    markets[mname] += 1
                bname = str((o.get("bookmaker") or {}).get("name") or "unknown")
                books[bname] += 1
                odds_rows += 1

    return {
        "source": "sportmonks_cache",
        "fixtures": fixtures,
        "odds_rows": odds_rows,
        "markets": dict(markets.most_common(40)),
        "bookmakers": dict(books.most_common(25)),
        "leagues": dict(leagues.most_common(20)),
        "seasons": dict(seasons.most_common(20)),
        "notes": "Cached Sportmonks payloads (UEFA + xG + pressure feature stores)",
    }


def _scan_odds_snapshots() -> dict[str, Any]:
    if not DB_PATH.is_file():
        return {"source": "odds_snapshots", "fixtures": 0, "odds_rows": 0, "notes": "DB missing"}

    conn = sqlite3.connect(DB_PATH)
    total_rows = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    fixtures = conn.execute("SELECT COUNT(DISTINCT fixture_id) FROM odds_snapshots").fetchone()[0]
    comp = dict(conn.execute("SELECT competition_key, COUNT(*) FROM odds_snapshots GROUP BY competition_key").fetchall())
    markets: Counter[str] = Counter()
    books: Counter[str] = Counter()
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
        lines = normalize_snapshot_odds_lines(payload, fixture_id=int(fid))
        for line in lines:
            markets[line.market_name] += 1
            books[line.bookmaker] += 1

    conn.close()
    return {
        "source": "odds_snapshots",
        "fixtures": fixtures,
        "odds_rows": total_rows,
        "normalized_lines": sum(markets.values()),
        "markets": dict(markets.most_common(30)),
        "bookmakers": dict(books.most_common(20)),
        "competition_keys": comp,
        "notes": "SQLite odds_snapshots (API-Football / The Odds API)",
    }


def _scan_oddalerts() -> dict[str, Any]:
    if not DB_PATH.is_file():
        return {"source": "oddalerts_odds_history", "fixtures": 0, "odds_rows": 0}

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM oddalerts_odds_history").fetchone()[0]
    fixtures = conn.execute("SELECT COUNT(DISTINCT oddalerts_fixture_id) FROM oddalerts_odds_history").fetchone()[0]
    markets = dict(conn.execute("SELECT market, COUNT(*) FROM oddalerts_odds_history GROUP BY market ORDER BY 2 DESC").fetchall())
    books = dict(conn.execute("SELECT bookmaker, COUNT(*) FROM oddalerts_odds_history GROUP BY bookmaker ORDER BY 2 DESC LIMIT 20").fetchall())
    leagues = dict(conn.execute("SELECT league, COUNT(*) FROM oddalerts_odds_history GROUP BY league").fetchall())
    seasons = dict(conn.execute("SELECT season, COUNT(*) FROM oddalerts_odds_history GROUP BY season").fetchall())
    conn.close()

    return {
        "source": "oddalerts_odds_history",
        "fixtures": fixtures,
        "odds_rows": total,
        "markets": markets,
        "bookmakers": books,
        "leagues": leagues,
        "seasons": {str(k): v for k, v in seasons.items()},
        "notes": "OddAlerts historical odds ingest (opening/closing/peak)",
    }


def run_inventory() -> InventorySummary:
    sources = [_scan_sportmonks_cache(), _scan_odds_snapshots(), _scan_oddalerts()]
    summary = InventorySummary(sources=sources)

    total_rows = 0
    markets: Counter[str] = Counter()
    books: Counter[str] = Counter()
    leagues: Counter[str] = Counter()
    seasons: Counter[str] = Counter()

    for src in sources:
        total_rows += int(src.get("odds_rows") or 0)
        for k, v in (src.get("markets") or {}).items():
            markets[k] += int(v)
        for k, v in (src.get("bookmakers") or {}).items():
            books[k] += int(v)
        for k, v in (src.get("leagues") or {}).items():
            leagues[k] += int(v)
        for k, v in (src.get("seasons") or {}).items():
            seasons[k] += int(v)
        for k, v in (src.get("competition_keys") or {}).items():
            leagues[k] += int(v)

    summary.total_snapshot_rows = total_rows
    summary.total_selections = sum(markets.values())
    summary.markets = dict(markets.most_common(50))
    summary.bookmakers = dict(books.most_common(30))
    summary.leagues = dict(leagues.most_common(30))
    summary.seasons = dict(seasons.most_common(20))
    return summary
