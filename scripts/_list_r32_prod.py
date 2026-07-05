#!/usr/bin/env python3
import sqlite3, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
c = sqlite3.connect(str(ROOT / "data" / "football_intelligence.db"))
c.row_factory = sqlite3.Row
print("count", c.execute("SELECT COUNT(*) FROM fixtures WHERE competition_key='world_cup_2026'").fetchone()[0])
rows = c.execute(
    "SELECT fixture_id,home_team,away_team,status,round_name,kickoff_utc FROM fixtures "
    "WHERE competition_key='world_cup_2026' AND round_name LIKE '%32%' ORDER BY kickoff_utc"
).fetchall()
print(json.dumps([dict(r) for r in rows], indent=2))
