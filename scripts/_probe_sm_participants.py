import json, sqlite3, runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT sportmonks_fixture_id, fixture_id_api_football, raw_json FROM sportmonks_fixture_enrichment WHERE fixture_id_api_football=1489386"
).fetchone()
data = json.loads(row["raw_json"]).get("data", {})
parts = data.get("participants") or []
print("fixture", row["fixture_id_api_football"])
for p in parts:
    print(p.get("name"), p.get("id"), (p.get("meta") or {}).get("location"))
