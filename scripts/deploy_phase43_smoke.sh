#!/usr/bin/env bash
# Phase 43 production smoke
set -euo pipefail

LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-https://footballpredictor.it.com}"

fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Phase 43 smoke ==="

HEALTH=$(curl -sS -o /tmp/phase43_health.json -w '%{http_code}' "${LOCAL_API}/api/health")
[ "$HEALTH" = "200" ] || fail "health status=${HEALTH}"
pass "/api/health 200"

python3 <<'PY'
import os
from pathlib import Path
env = Path("/opt/worldcup-predictor/.env.production").read_text(encoding="utf-8")
key = ""
for line in env.splitlines():
    if line.startswith("WEATHER_API_KEY="):
        key = line.split("=", 1)[1].strip()
        break
assert key, "WEATHER_API_KEY missing"
assert "secret" not in key.lower()
print("weather_key_len=", len(key))
PY
pass "weather config detected"

ACC=$(curl -sS -o /tmp/phase43_acc.json -w '%{http_code}' "${LOCAL_API}/api/accuracy/summary")
[ "$ACC" = "200" ] || fail "accuracy summary status=${ACC}"
pass "/api/accuracy/summary 200"

LOGIN=$(curl -sS -o /tmp/phase43_login.json -w '%{http_code}' \
  -X POST "${LOCAL_API}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"nonexistent-smoke@test.local","password":"wrong"}')
[ "$LOGIN" = "401" ] || [ "$LOGIN" = "400" ] || [ "$LOGIN" = "422" ] || fail "login status=${LOGIN}"
pass "login endpoint ${LOGIN}"

REG=$(curl -sS -o /dev/null -w '%{http_code}' \
  -X POST "${LOCAL_API}/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"","password":""}')
[ "$REG" = "400" ] || [ "$REG" = "422" ] || fail "register status=${REG}"
pass "register endpoint ${REG}"

HIST=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/user/prediction-history")
[ "$HIST" = "401" ] || [ "$HIST" = "403" ] || fail "history auth broken status=${HIST}"
pass "history detail auth gate ${HIST}"

PAGE=$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_URL}/accuracy")
[ "$PAGE" = "200" ] || fail "accuracy page status=${PAGE}"
pass "/accuracy page 200"

PRED_PAGE=$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_URL}/prediction/1489393")
[ "$PRED_PAGE" = "200" ] || fail "prediction page status=${PRED_PAGE}"
pass "prediction detail page 200"

BUNDLE=$(python3 <<'PY'
import re
from pathlib import Path
html = Path("/var/www/worldcup/frontend/dist/index.html").read_text()
m = re.search(r'/assets/(index-[^"]+\.js)', html)
print(m.group(1) if m else "")
PY
)
BUNDLE_PATH="/var/www/worldcup/frontend/dist/assets/${BUNDLE}"
if [ -n "$BUNDLE" ] && [ -f "$BUNDLE_PATH" ]; then
  if grep -q 'Weather Intelligence' "$BUNDLE_PATH" 2>/dev/null; then
    pass "frontend bundle has Weather Intelligence section"
  else
    fail "frontend bundle missing Weather Intelligence"
  fi
  if grep -q 'weather_intelligence' "$BUNDLE_PATH" 2>/dev/null; then
    pass "frontend bundle references weather_intelligence"
  else
    fail "frontend bundle missing weather_intelligence"
  fi
  if grep -qE '74aa6ff983e54d90a3f92638252702|WEATHER_API_KEY' "$BUNDLE_PATH" 2>/dev/null; then
    fail "API key leaked in frontend bundle"
  else
    pass "no API key in frontend bundle"
  fi
fi

cd /opt/worldcup-predictor
sudo -u www-data env PYTHONPATH=/opt/worldcup-predictor APP_ENV=production bash -lc \
  'cd /opt/worldcup-predictor && set -a && source .env.production && set +a && .venv/bin/python scripts/_phase43_prod_weather_smoke.py' \
  2>&1 | tee /tmp/phase43_weather_smoke.log
grep -q 'WEATHER_SMOKE_PASS' /tmp/phase43_weather_smoke.log || fail "weather prediction smoke failed"
pass "prediction payload weather_intelligence"

echo "SMOKE_ALL_PASS"
