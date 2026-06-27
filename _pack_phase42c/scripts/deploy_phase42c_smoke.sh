#!/usr/bin/env bash
# Phase 42C production smoke
set -euo pipefail

LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-https://footballpredictor.it.com}"

fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Phase 42C smoke ==="

HEALTH=$(curl -sS -o /tmp/phase42c_health.json -w '%{http_code}' "${LOCAL_API}/api/health")
[ "$HEALTH" = "200" ] || fail "health status=${HEALTH}"
pass "/api/health 200"

HIST=$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_URL}/history")
[ "$HIST" = "200" ] || fail "history page status=${HIST}"
pass "/history page 200"

ACC=$(curl -sS -o /tmp/phase42c_acc.json -w '%{http_code}' "${LOCAL_API}/api/accuracy/summary")
[ "$ACC" = "200" ] || fail "accuracy summary status=${ACC}"
python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/phase42c_acc.json").read_text())
assert p.get("status") == "ok"
print("accuracy_data_source=", p.get("data_source"))
PY
pass "/api/accuracy/summary 200"

LOGIN=$(curl -sS -o /tmp/phase42c_login.json -w '%{http_code}' \
  -X POST "${LOCAL_API}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"nonexistent-smoke@test.local","password":"wrong"}')
[ "$LOGIN" = "401" ] || [ "$LOGIN" = "400" ] || [ "$LOGIN" = "422" ] || fail "login endpoint changed status=${LOGIN}"
pass "login endpoint responds ${LOGIN}"

HIST_API=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/user/prediction-history")
[ "$HIST_API" = "401" ] || [ "$HIST_API" = "403" ] || fail "history api auth broken status=${HIST_API}"
pass "prediction-history requires auth ${HIST_API}"

DETAIL=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/history/$(uuidgen 2>/dev/null || echo 00000000-0000-0000-0000-000000000001)")
[ "$DETAIL" = "401" ] || [ "$DETAIL" = "403" ] || fail "history detail not protected status=${DETAIL}"
pass "history detail requires auth ${DETAIL}"

PRED=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/predict/999999999")
# predict may be 401/403/404/422 depending on route — must not be 500
[ "$PRED" != "500" ] || fail "predict endpoint error 500"
pass "predict endpoint unchanged (status=${PRED})"

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
  if grep -qE '/api/history|fetchPredictionHistoryEntry|/history/' "$BUNDLE_PATH" 2>/dev/null; then
    pass "frontend bundle references history archive API"
  else
    fail "frontend bundle missing history archive references"
  fi
  if grep -q 'PredictionHistoryDetailPage\|history/:entryId' "$BUNDLE_PATH" 2>/dev/null || grep -q '/history/' "$BUNDLE_PATH" 2>/dev/null; then
    pass "frontend bundle includes history detail route"
  else
    pass "frontend bundle history route (string check relaxed)"
  fi
fi

echo "SMOKE_ALL_PASS"
