import sqlite3, json
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT endpoint, params_json, length(payload_json) sz FROM api_response_cache "
    "WHERE endpoint LIKE '%fixtures%' LIMIT 15"
).fetchall()
for r in rows:
    print(r["endpoint"], r["params_json"][:100] if r["params_json"] else None, r["sz"])
rows2 = conn.execute(
    "SELECT endpoint, params_json FROM api_response_cache WHERE endpoint LIKE '%headtohead%' OR params_json LIKE '%h2h%' LIMIT 5"
).fetchall()
print("h2h rows", len(rows2))
for r in rows2:
    print(r["endpoint"], r["params_json"][:120])
