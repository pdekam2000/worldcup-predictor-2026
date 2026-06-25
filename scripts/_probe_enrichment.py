import sqlite3, runpy, json
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute("SELECT fixture_id, home_team_id, away_team_id, lineups_json FROM fixture_enrichment LIMIT 5").fetchall()
    for r in rows:
        print(dict(r))
except Exception as e:
    print("err", e)
    cols = conn.execute("PRAGMA table_info(fixture_enrichment)").fetchall()
    print([c[1] for c in cols])
