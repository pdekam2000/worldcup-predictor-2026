"""
Import Sportmonks dump odds into odds_snapshots table for backtest use.
Maps Sportmonks fixture names to internal fixture_ids via team name matching.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DUMP_DIR = Path("data/sportmonks_dump")
DB_PATH = "data/football_intelligence.db"


def normalize(name: str) -> str:
    return name.lower().strip().replace("-", " ").replace(".", "")


def build_team_index(conn: sqlite3.Connection) -> dict[str, list[int]]:
    """Build index: normalized_team_name -> [fixture_ids]"""
    rows = conn.execute("""
        SELECT fixture_id, home_team, away_team FROM fixtures
        WHERE is_placeholder = 0
    """).fetchall()
    index: dict[str, list[int]] = {}
    for fid, home, away in rows:
        for name in [home, away]:
            key = normalize(name)
            index.setdefault(key, []).append(fid)
    return index


def find_internal_fixture(
    home: str, away: str, kickoff: str,
    team_index: dict[str, list[int]],
    conn: sqlite3.Connection,
) -> int | None:
    """Find internal fixture_id by matching home+away team names and date."""
    home_ids = set(team_index.get(normalize(home), []))
    away_ids = set(team_index.get(normalize(away), []))
    candidates = home_ids & away_ids
    if not candidates:
        return None

    # اگه چند تا candidate داریم، با تاریخ مچ کن
    if len(candidates) == 1:
        return candidates.pop()

    date_prefix = kickoff[:10] if kickoff else ""
    if date_prefix:
        rows = conn.execute(f"""
            SELECT fixture_id FROM fixtures
            WHERE fixture_id IN ({','.join(str(i) for i in candidates)})
            AND kickoff_utc LIKE ?
        """, (f"{date_prefix}%",)).fetchall()
        if rows:
            return rows[0][0]

    return candidates.pop()


def extract_participants(fixture: dict) -> tuple[str, str]:
    """Extract home/away team names from participants."""
    participants = fixture.get("participants", [])
    home, away = "", ""
    for p in participants:
        meta = p.get("meta", {})
        location = meta.get("location", "")
        name = p.get("name", "")
        if location == "home":
            home = name
        elif location == "away":
            away = name
    return home, away


def build_odds_payload(fixture: dict) -> dict:
    """Convert Sportmonks odds to odds_snapshots payload format."""
    odds = fixture.get("odds", [])
    bookmakers: dict[int, dict] = {}

    for odd in odds:
        bm_id = odd.get("bookmaker_id")
        if not bm_id:
            continue
        if bm_id not in bookmakers:
            bookmakers[bm_id] = {"bookmaker_id": bm_id, "bets": {}}

        market_desc = odd.get("market_description", "")
        label = odd.get("label", "")
        value = odd.get("value", "0")

        bet_key = market_desc
        if bet_key not in bookmakers[bm_id]["bets"]:
            bookmakers[bm_id]["bets"][bet_key] = []

        bookmakers[bm_id]["bets"][bet_key].append({
            "label": label,
            "value": value,
            "probability": odd.get("probability", ""),
        })

    return {
        "source": "sportmonks",
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "bookmakers": list(bookmakers.values()),
    }


def import_season(
    conn: sqlite3.Connection,
    team_index: dict[str, list[int]],
    league: str,
    season: str,
    season_dir: Path,
) -> dict:
    files = [f for f in season_dir.glob("*.json") if f.name != "_manifest.json"]
    mapped = 0
    skipped = 0
    no_match = 0
    no_odds = 0

    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            fixture = raw.get("data", raw)
        except Exception as exc:
            logger.warning(f"Failed to read {f}: {exc}")
            skipped += 1
            continue

        odds = fixture.get("odds", [])
        if not odds:
            no_odds += 1
            continue

        home, away = extract_participants(fixture)
        kickoff = fixture.get("starting_at", "")

        internal_id = find_internal_fixture(home, away, kickoff, team_index, conn)
        if not internal_id:
            no_match += 1
            continue

        # چک کن قبلاً import شده؟
        existing = conn.execute("""
            SELECT id FROM odds_snapshots
            WHERE fixture_id = ? AND competition_key = ?
            AND snapshot_at LIKE 'sportmonks%'
        """, (internal_id, league)).fetchone()
        if existing:
            skipped += 1
            continue

        payload = build_odds_payload(fixture)
        conn.execute("""
            INSERT INTO odds_snapshots
            (fixture_id, competition_key, snapshot_at, payload_json)
            VALUES (?, ?, ?, ?)
        """, (
            internal_id,
            league,
            f"sportmonks_{kickoff[:10]}",
            json.dumps(payload, ensure_ascii=False),
        ))
        mapped += 1

    conn.commit()
    return {
        "total_files": len(files),
        "mapped": mapped,
        "skipped": skipped,
        "no_match": no_match,
        "no_odds": no_odds,
    }


def run_import(db_path: str = DB_PATH, dump_dir: Path = DUMP_DIR):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    team_index = build_team_index(conn)
    logger.info(f"Team index built: {len(team_index)} entries")

    total_mapped = 0

    for manifest_path in sorted(dump_dir.rglob("_manifest.json")):
        season_dir = manifest_path.parent
        parts = season_dir.relative_to(dump_dir).parts
        if len(parts) != 2:
            continue
        league, season = parts

        logger.info(f"\n=== {league}/{season} ===")
        result = import_season(conn, team_index, league, season, season_dir)
        total_mapped += result["mapped"]
        logger.info(
            f"mapped={result['mapped']} | skipped={result['skipped']} | "
            f"no_match={result['no_match']} | no_odds={result['no_odds']}"
        )

    conn.close()
    logger.info(f"\nDone! Total mapped: {total_mapped} fixtures")


if __name__ == "__main__":
    run_import()
