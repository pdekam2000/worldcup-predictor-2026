"""Scan all known odds sources for goalscorer markets."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.market_classifier import classify_market, is_goalscorer_market_text
from worldcup_predictor.egie.goalscorer_odds_acquisition.models import SourceInventory
from worldcup_predictor.egie.goalscorer_odds_mapping.audit import _extract_selections, _FINISHED, scan_cache_odds
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import normalize_snapshot_odds_lines
from worldcup_predictor.intelligence.phase54i_discovery.auditors import audit_fixture_blob

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "football_intelligence.db"

_SPORTMONKS_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_API_GS_MARKET = re.compile(r"(anytime|first|last)\s+goal\s+scorer|goalscorers?", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _inventory_from_sportmonks_strict() -> SourceInventory:
    rows, summary = scan_cache_odds()
    markets = Counter(r.market for r in rows)
    books = Counter(r.bookmaker for r in rows)
    return SourceInventory(
        source="sportmonks_cache_strict",
        fixtures_audited=summary.fixtures_audited,
        fixtures_with_goalscorer_odds=summary.fixtures_with_goalscorer_odds,
        selection_count=summary.selection_count,
        market_count=summary.market_count,
        bookmaker_count=summary.bookmaker_count,
        notes="Sportmonks cached payloads — player/team goalscorer markets (54M strict patterns)",
        markets=dict(markets),
        bookmakers=dict(books),
    )


def _inventory_from_sportmonks_broad() -> SourceInventory:
    seen: set[int] = set()
    fixtures_with_gs = 0
    selection_count = 0
    markets: Counter[str] = Counter()
    books: set[str] = set()
    audited = 0

    for root in _SPORTMONKS_CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            blob = _load_json(path)
            if not isinstance(blob, dict):
                continue
            audit = audit_fixture_blob(blob)
            if not audit.get("valid"):
                continue
            fid = int(audit.get("sportmonks_fixture_id") or 0)
            if fid in seen:
                continue
            seen.add(fid)
            audited += 1
            gs = audit.get("goalscorer_odds") or {}
            if not gs.get("has_goalscorer_odds"):
                continue
            fixtures_with_gs += 1
            selection_count += int(gs.get("goalscorer_market_rows") or 0)
            for mname, cnt in (gs.get("markets") or {}).items():
                markets[mname] += int(cnt)
            books.update(range(gs.get("bookmakers") or 0))

    return SourceInventory(
        source="sportmonks_cache_broad",
        fixtures_audited=audited,
        fixtures_with_goalscorer_odds=fixtures_with_gs,
        selection_count=selection_count,
        market_count=len(markets),
        bookmaker_count=len(books) if books else 0,
        notes="Sportmonks cache — broad 54I patterns (includes FTS, correct score, etc.)",
        markets=dict(markets.most_common(30)),
        bookmakers={},
    )


def _scan_api_football_payload(
  payload: Any,
  *,
  fixture_id: int | None,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    lines = normalize_snapshot_odds_lines(payload, fixture_id=fixture_id)
    gs_lines = [l for l in lines if _API_GS_MARKET.search(l.market_name)]
    rows: list[dict[str, Any]] = []
    markets: set[str] = set()
    books: set[str] = set()
    for line in gs_lines:
        markets.add(line.market_name)
        books.add(line.bookmaker)
        rows.append(
            {
                "fixture_id": fixture_id,
                "source": "api_football",
                "bookmaker": line.bookmaker,
                "market": line.market_name,
                "selection": line.selection,
                "odds": line.odd,
            }
        )
    return rows, markets, books


def _inventory_from_odds_snapshots() -> SourceInventory:
    if not DB_PATH.is_file():
        return SourceInventory(source="api_football_odds_snapshots", notes="DB not found")

    conn = sqlite3.connect(DB_PATH)
    seen: set[int] = set()
    fixtures_with_gs = 0
    selection_count = 0
    markets: Counter[str] = Counter()
    books: Counter[str] = Counter()
    audited = 0

    for fid, payload_json in conn.execute("SELECT fixture_id, payload_json FROM odds_snapshots").fetchall():
        if fid in seen:
            continue
        seen.add(fid)
        audited += 1
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        rows, mset, bset = _scan_api_football_payload(payload, fixture_id=int(fid))
        if rows:
            fixtures_with_gs += 1
            selection_count += len(rows)
            for r in rows:
                markets[r["market"]] += 1
                books[r["bookmaker"]] += 1

    conn.close()
    return SourceInventory(
        source="api_football_odds_snapshots",
        fixtures_audited=audited,
        fixtures_with_goalscorer_odds=fixtures_with_gs,
        selection_count=selection_count,
        market_count=len(markets),
        bookmaker_count=len(books),
        notes="SQLite odds_snapshots table (API-Football / The Odds API payloads)",
        markets=dict(markets.most_common(20)),
        bookmakers=dict(books.most_common(15)),
    )


def _inventory_from_api_cache() -> SourceInventory:
    try:
        from worldcup_predictor.backtesting.phase31e_backfill import collect_cached_odds_sources
        from worldcup_predictor.cache.api_cache import ApiCache
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        settings = get_settings()
        repo = FootballIntelligenceRepository()
        disk = ApiCache(Path(settings.api_cache_dir)) if settings.api_cache_dir else None
        sources = collect_cached_odds_sources(repo, disk_cache=disk)
        repo.close()
    except Exception as exc:
        return SourceInventory(source="api_football_disk_cache", notes=f"scan failed: {exc}")

    fixtures_with_gs = 0
    selection_count = 0
    markets: Counter[str] = Counter()
    books: Counter[str] = Counter()

    for fid, entry in sources.items():
        if not isinstance(entry, dict):
            continue
        payload: Any = entry.get("payload") or entry
        if "bookmakers" in entry and "payload" not in entry:
            payload = {"api_sports": {"bookmakers": entry.get("bookmakers")}}
        rows, _, _ = _scan_api_football_payload(payload, fixture_id=int(fid))
        if rows:
            fixtures_with_gs += 1
            selection_count += len(rows)
            for r in rows:
                markets[r["market"]] += 1
                books[r["bookmaker"]] += 1

    return SourceInventory(
        source="api_football_disk_cache",
        fixtures_audited=len(sources),
        fixtures_with_goalscorer_odds=fixtures_with_gs,
        selection_count=selection_count,
        market_count=len(markets),
        bookmaker_count=len(books),
        notes=f"Disk cache at {settings.api_cache_dir}",
        markets=dict(markets.most_common(20)),
        bookmakers=dict(books.most_common(15)),
    )


def _inventory_from_raw_cache_files() -> SourceInventory:
    """Walk .cache/api_football for odds JSON not indexed in collect_cached_odds_sources."""
    cache_root = ROOT / ".cache" / "api_football"
    if not cache_root.is_dir():
        return SourceInventory(source="api_football_raw_cache_walk", notes="No .cache/api_football")

    fixtures_with_gs = 0
    selection_count = 0
    markets: Counter[str] = Counter()
    audited = 0
    seen_fixtures: set[int] = set()

    for path in cache_root.rglob("*.json"):
        blob = _load_json(path)
        if not isinstance(blob, dict):
            continue
        audited += 1
        text = json.dumps(blob).lower()
        if not is_goalscorer_market_text(text):
            continue
        # Try to extract fixture id from path or payload
        fid = None
        for key in ("fixture", "fixture_id", "id"):
            val = blob.get(key)
            if isinstance(val, int):
                fid = val
                break
        if fid is None:
            m = re.search(r"fixture[_-]?(\d+)", path.name, re.I)
            fid = int(m.group(1)) if m else audited
        if fid in seen_fixtures:
            continue
        rows, _, _ = _scan_api_football_payload(blob, fixture_id=fid)
        if not rows:
            # check nested response shapes
            resp = blob.get("response")
            if isinstance(resp, list) and resp:
                rows, _, _ = _scan_api_football_payload({"response": resp}, fixture_id=fid)
        if rows:
            seen_fixtures.add(fid)
            fixtures_with_gs += 1
            selection_count += len(rows)
            for r in rows:
                markets[r["market"]] += 1

    return SourceInventory(
        source="api_football_raw_cache_walk",
        fixtures_audited=audited,
        fixtures_with_goalscorer_odds=fixtures_with_gs,
        selection_count=selection_count,
        market_count=len(markets),
        bookmaker_count=0,
        notes="Full .cache/api_football walk — text prefilter then strict market parse",
        markets=dict(markets.most_common(20)),
        bookmakers={},
    )


def _inventory_from_shadow_replays() -> SourceInventory:
    shadow_paths = [
        ROOT / "data" / "shadow" / "phase16_odds_primary_replay.jsonl",
        ROOT / "data" / "shadow" / "phase54c1_pl_odds_backfill_manifest.jsonl",
    ]
    fixtures_with_gs = 0
    selection_count = 0
    markets: Counter[str] = Counter()
    audited = 0
    seen: set[str] = set()

    for path in shadow_paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            audited += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = json.dumps(row, sort_keys=True)[:200]
            if key in seen:
                continue
            seen.add(key)
            text = json.dumps(row).lower()
            if not is_goalscorer_market_text(text):
                continue
            fixtures_with_gs += 1
            selection_count += 1
            for token in ("goalscorer", "goal scorer", "player to score"):
                if token in text:
                    markets[token] += 1

    return SourceInventory(
        source="shadow_odds_replays",
        fixtures_audited=audited,
        fixtures_with_goalscorer_odds=fixtures_with_gs,
        selection_count=selection_count,
        market_count=len(markets),
        bookmaker_count=0,
        notes="Shadow replay JSONL — keyword presence only (no structured GS parse)",
        markets=dict(markets),
        bookmakers={},
    )


def build_inventory() -> dict[str, Any]:
    """Audit all sources and return consolidated inventory."""
    sources = [
        _inventory_from_sportmonks_strict(),
        _inventory_from_sportmonks_broad(),
        _inventory_from_odds_snapshots(),
        _inventory_from_api_cache(),
        _inventory_from_raw_cache_files(),
        _inventory_from_shadow_replays(),
    ]

    # Deduplicated best estimate: union of strict sportmonks + api snapshots (different ID spaces)
    strict_sm = next(s for s in sources if s.source == "sportmonks_cache_strict")
    api_snaps = next(s for s in sources if s.source == "api_football_odds_snapshots")

    totals = {
        "fixture_count_union_estimate": strict_sm.fixtures_with_goalscorer_odds + api_snaps.fixtures_with_goalscorer_odds,
        "selection_count_union_estimate": strict_sm.selection_count + api_snaps.selection_count,
        "market_count_union_estimate": max(strict_sm.market_count, api_snaps.market_count),
        "bookmaker_count_union_estimate": max(strict_sm.bookmaker_count, api_snaps.bookmaker_count),
        "sportmonks_strict_fixtures": strict_sm.fixtures_with_goalscorer_odds,
        "api_football_fixtures": api_snaps.fixtures_with_goalscorer_odds,
    }

    return {
        "generated_at": _utc_now(),
        "sources": [s.to_dict() for s in sources],
        "totals": totals,
        "summary": {
            "fixture_count": totals["fixture_count_union_estimate"],
            "selection_count": totals["selection_count_union_estimate"],
            "market_count": totals["market_count_union_estimate"],
            "bookmaker_count": totals["bookmaker_count_union_estimate"],
        },
    }


def collect_normalized_rows_for_split() -> list[dict[str, Any]]:
    """Gather normalized GS rows from sportmonks strict + api snapshots for market split."""
    rows: list[dict[str, Any]] = []

    sm_rows, _ = scan_cache_odds()
    for r in sm_rows:
        rows.append(
            {
                "source": "sportmonks_cache_strict",
                "fixture_id": r.sportmonks_fixture_id,
                "bookmaker": r.bookmaker,
                "market": r.market,
                "label": r.label,
                "selection": r.selection_name,
            }
        )

    if DB_PATH.is_file():
        conn = sqlite3.connect(DB_PATH)
        seen: set[int] = set()
        for fid, payload_json in conn.execute("SELECT fixture_id, payload_json FROM odds_snapshots").fetchall():
            if fid in seen:
                continue
            seen.add(fid)
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
            api_rows, _, _ = _scan_api_football_payload(payload, fixture_id=int(fid))
            rows.extend(api_rows)
        conn.close()

    return rows
