#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
IP=91.107.188.229

echo "=== Public health ==="
curl -sf "http://$IP/api/health"
echo

echo "=== Local predict smoke ==="
curl -sf -X POST "http://127.0.0.1:8000/api/predict/1539007" -o /tmp/pred.json
"$APP/.venv/bin/python" <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/pred.json").read_text())
checks = [
    ("status_ok", d.get("status") == "ok"),
    ("recommended_bets", isinstance(d.get("recommended_bets"), list)),
    ("detailed_markets", isinstance(d.get("detailed_markets"), dict)),
    ("market_ranking", isinstance(d.get("market_ranking"), list)),
    ("safe_pick", "safe_pick" in d),
    ("value_pick", "value_pick" in d),
    ("aggressive_pick", "aggressive_pick" in d),
    ("ou_probabilities", "over_under_2_5" in (d.get("probabilities") or {})),
    ("btts_probabilities", "btts" in (d.get("probabilities") or {})),
]
for name, ok in checks:
    print("PASS" if ok else "FAIL", name)
print("safe_pick:", (d.get("safe_pick") or {}).get("pick"))
print("value_pick:", (d.get("value_pick") or {}).get("pick"))
print("recommended:", [b.get("pick") for b in d.get("recommended_bets", []) if b.get("status") == "recommended"])
print("ou:", d.get("probabilities", {}).get("over_under_2_5"))
print("btts:", d.get("probabilities", {}).get("btts"))
print("ranking_count:", len(d.get("market_ranking") or []))
if not all(c[1] for c in checks):
    raise SystemExit(1)
PY

echo "=== Frontend bundle ==="
grep -rl "Ranked Picks" /var/www/worldcup/frontend/dist/assets/*.js | head -1 || echo "Ranked Picks string not found"
grep -rl "Prediction History" /var/www/worldcup/frontend/dist/assets/*.js | head -1 || true

echo "=== Matches upcoming ==="
curl -sf "http://$IP/api/matches/upcoming?limit=3" | head -c 400
echo

echo "=== Git commit on server ==="
cd "$APP" && git log -1 --oneline

echo "=== Service ==="
systemctl is-active worldcup-api

echo "ALL_VERIFY_OK"
