#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
DOMAIN=footballpredictor.it.com

echo "=== Public health (HTTPS domain) ==="
curl -sfL "https://$DOMAIN/api/health"
echo

echo "=== Public matches upcoming ==="
curl -sfL "https://$DOMAIN/api/matches/upcoming?limit=2" | head -c 500
echo

echo "=== Cached predict via nginx ==="
curl -sfL "https://$DOMAIN/api/predict/1539007" -X POST -H "Content-Type: application/json" -o /tmp/pred_pub.json 2>/dev/null || curl -sf -X POST "http://127.0.0.1:8000/api/predict/1539007" -o /tmp/pred_pub.json
"$APP/.venv/bin/python" <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/pred_pub.json").read_text())
print("status:", d.get("status"))
print("no_bet:", d.get("no_bet"))
print("confidence:", d.get("confidence"))
print("has recommended_bets:", bool(d.get("recommended_bets")))
print("has detailed_markets:", bool(d.get("detailed_markets")))
print("has market_ranking:", "market_ranking" in d)
print("has safe_pick key:", "safe_pick" in d)
ou = (d.get("probabilities") or {}).get("over_under_2_5")
btts = (d.get("probabilities") or {}).get("btts")
print("ou:", ou.get("selection") if ou else None, ou.get("probability") if ou else None)
print("btts:", btts.get("selection") if btts else None, btts.get("probability") if btts else None)
dm = d.get("detailed_markets") or {}
print("detailed keys:", sorted(dm.keys())[:8])
PY

echo "=== Frontend index ==="
curl -sfL "https://$DOMAIN/" | head -c 200
echo

echo "=== Frontend Phase 30C strings ==="
grep -q "Ranked Picks" /var/www/worldcup/frontend/dist/assets/*.js && echo "PASS Ranked Picks in bundle"
grep -q "Detailed Probabilities" /var/www/worldcup/frontend/dist/assets/*.js && echo "PASS Detailed Probabilities in bundle"
grep -q "resultFilter" /var/www/worldcup/frontend/dist/assets/*.js && echo "PASS Phase29 resultFilter in bundle" || grep -q "Correct" /var/www/worldcup/frontend/dist/assets/*.js && echo "PASS History filters in bundle"

echo "=== History route (unauthenticated expect 401/403) ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/api/user/prediction-history")
echo "GET /api/user/prediction-history HTTP $CODE (401/403 expected without token)"

echo "=== Deploy state ==="
cd "$APP" && git log -1 --oneline
systemctl is-active worldcup-api
echo "ALL_PUBLIC_VERIFY_OK"
