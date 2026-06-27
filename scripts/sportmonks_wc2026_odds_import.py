"""Import Sportmonks WC 2026 odds into odds_snapshots."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DUMP_DIR = Path("data/sportmonks_dump/world_cup/2026")
DB_PATH = "data/football_intelligence.db"


def normalize(name: str) -> str:
    return name.lower().strip().replace("-", " ").replace(".", "").replace("'", "")


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # لود همه WC 2026 fixtures از DB
    db_fixtures = conn.execute("""
        SELECT fixture_id, home_team, away_team, kickoff_utc
        FROM fixtures
        WHERE competition_key = 'world_cup_2026'
        AND kickoff_utc > '2026-01-01'
        AND is_placeholder = 0
    """).fetchall()

    # index: (norm_home, norm_away) -> fixture_id
    db_index: dict[tuple[str, str], int] = {}
    for f in db_fixtures:
        key = (normalize(f["home_team"]), normalize(f["away_team"]))
        db_index[key] = f["fixture_id"]

    logger.info(f"DB WC 2026 fixtures: {len(db_fixtures)}")

    files = [f for f in DUMP_DIR.glob("*.json") if f.name != "_manifest.json"]
    logger.info(f"Dump files: {len(files)}")

    mapped = 0
    no_match = 0
    skipped = 0

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        fixture = data.get("data", data)

        odds = fixture.get("odds", [])
        if not odds:
            continue

        # participants
        home, away = "", ""
        for p in fixture.get("participants", []):
            loc = p.get("meta", {}).get("location", "")
            if loc == "home":
                home = p.get("name", "")
            elif loc == "away":
                away = p.get("name", "")

        key = (normalize(home), normalize(away))
        internal_id = db_index.get(key)

        if not internal_id:
            # try reverse
            rev_key = (normalize(away), normalize(home))
            internal_id = db_index.get(rev_key)

        if not internal_id:
            logger.debug(f"No match: {home} vs {away}")
            no_match += 1
            continue

        # چک duplicate
        existing = conn.execute("""
            SELECT id FROM odds_snapshots
            WHERE fixture_id = ? AND snapshot_at LIKE 'sportmonks_wc2026%'
        """, (internal_id,)).fetchone()

        if existing:
            skipped += 1
            continue

        # build payload
        bookmakers: dict[int, dict] = {}
        for odd in odds:
            bm_id = odd.get("bookmaker_id")
            if not bm_id:
                continue
            if bm_id not in bookmakers:
                bookmakers[bm_id] = {"bookmaker_id": bm_id, "bets": []}
            bookmakers[bm_id]["bets"].append({
                "market": odd.get("market_description", ""),
                "label": odd.get("label", ""),
                "value": odd.get("value", ""),
                "probability": odd.get("probability", ""),
            })

        payload = json.dumps({
            "source": "sportmonks",
            "bookmakers": list(bookmakers.values()),
        }, ensure_ascii=False)

        conn.execute("""
            INSERT INTO odds_snapshots
            (fixture_id, competition_key, snapshot_at, payload_json)
            VALUES (?, ?, ?, ?)
        """, (internal_id, "world_cup_2026", f"sportmonks_wc2026_{fixture.get('starting_at','')[:10]}", payload))
        mapped += 1

    conn.commit()
    conn.close()

    logger.info(f"Done! mapped={mapped} | no_match={no_match} | skipped={skipped}")


if __name__ == "__main__":
    run()
