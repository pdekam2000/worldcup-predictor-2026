#!/usr/bin/env bash
set -euo pipefail
curl -sS -X POST "https://footballpredictor.it.com/api/predict/1489388" -H "Accept: application/json" -o /tmp/predict_cache.json -w "http_code:%{http_code}\n"
python3 <<'PY'
import json
d = json.load(open("/tmp/predict_cache.json"))
print("status:", d.get("status"))
print("cache_source:", d.get("cache_source"))
agents = (d.get("specialist_summary") or {}).get("agents") or {}
for key in ("injury_suspension_agent", "injury_suspension_intelligence_agent"):
    row = agents.get(key) or {}
    print(f"{key}: status={row.get('status')} reason={row.get('status_reason')}")
print("data_quality:", d.get("data_quality"))
PY
