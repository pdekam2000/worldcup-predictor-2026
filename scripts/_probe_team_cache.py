import json, sqlite3, runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT cache_key, endpoint, params_json, length(payload_json) sz FROM api_response_cache WHERE params_json LIKE '%team%'").fetchall()
print("team cache entries", len(rows))
for r in rows[:20]:
    print(r["endpoint"], r["params_json"], r["sz"])
