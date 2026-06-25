import json, sqlite3, runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))
from worldcup_predictor.cache.api_cache import ApiCache

conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
for fid in [1489371, 1489373, 1539014]:
    key = ApiCache.build_key("fixtures", {"id": fid})
    row = conn.execute("SELECT payload_json FROM api_response_cache WHERE cache_key=?", (key,)).fetchone()
    if not row:
        print(fid, "no cache")
        continue
    data = json.loads(row["payload_json"])
    resp = data.get("response") or data
    if isinstance(resp, list) and resp:
        item = resp[0]
    else:
        item = resp
    teams = item.get("teams") or {}
    league = item.get("league") or {}
    print(fid, teams.get("home",{}).get("name"), teams.get("home",{}).get("id"), teams.get("away",{}).get("name"), teams.get("away",{}).get("id"), league.get("name"))
