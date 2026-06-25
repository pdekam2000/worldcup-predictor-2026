#!/usr/bin/env bash
# Capture pre-deploy baseline predictions
set -euo pipefail
APP=/opt/worldcup-predictor
cd "$APP"
OUT="${1:-/tmp/phase32_pre_deploy_baseline.json}"
.venv/bin/python - <<'PY'
import json, urllib.request
fixtures = [
    (1539007, "Netherlands vs Sweden"),
    (1489393, "Germany vs Ivory Coast"),
]
extra = []
try:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    repo = FootballIntelligenceRepository()
    for r in repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=40):
        m = f"{r.get('home_team_name','')} vs {r.get('away_team_name','')}"
        if "France" in m or "Senegal" in m:
            extra.append((int(r["fixture_id"]), m))
except Exception as e:
    extra = [("error", str(e))]
all_f = fixtures + extra[:2]
results = []
for fid, label in all_f:
    if isinstance(fid, str):
        continue
    req = urllib.request.Request(f"http://127.0.0.1:8000/api/predict/{fid}", method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        d = json.loads(resp.read().decode())
    results.append({
        "fixture_id": fid, "label": label,
        "confidence": d.get("confidence"),
        "no_bet": d.get("no_bet"),
        "safe_pick": d.get("safe_pick"),
        "value_pick": d.get("value_pick"),
        "aggressive_pick": d.get("aggressive_pick"),
        "prediction": d.get("prediction"),
        "data_quality": d.get("data_quality"),
    })
print(json.dumps(results, indent=2))
PY
> "$OUT"
echo "Wrote $OUT"
