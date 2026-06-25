import json, sqlite3, runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))
from worldcup_predictor.cache.api_cache import ApiCache
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
key = ApiCache.build_key("fixtures", {"last": 10, "team": 10177})
row = conn.execute("SELECT payload_json FROM api_response_cache WHERE cache_key=?", (key,)).fetchone()
data = json.loads(row["payload_json"])
resp = data if isinstance(data, list) else data.get("response") or []
print("team 10177 name from first fixture:")
if resp:
    item = resp[0]
    teams = item.get("teams") or {}
    league = item.get("league") or {}
    for side in ("home","away"):
        t = teams.get(side) or {}
        if t.get("id") == 10177:
            print(" ", t.get("name"), league.get("name"))
    print(" sample leagues:", list({(x.get('league') or {}).get('name') for x in resp[:5]}))

key2 = ApiCache.build_key("fixtures/headtohead", {"h2h": "10177-27072", "last": 5})
row2 = conn.execute("SELECT payload_json FROM api_response_cache WHERE cache_key=?", (key2,)).fetchone()
h2h = json.loads(row2["payload_json"])
h2h_resp = h2h if isinstance(h2h, list) else h2h.get("response") or []
if h2h_resp:
    t = h2h_resp[0].get("teams") or {}
    print("h2h pair:", (t.get("home") or {}).get("name"), "vs", (t.get("away") or {}).get("name"))
