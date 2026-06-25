#!/usr/bin/env bash
# Phase 42D production smoke
set -euo pipefail

LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-https://footballpredictor.it.com}"

fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Phase 42D smoke ==="

HEALTH=$(curl -sS -o /tmp/phase42d_health.json -w '%{http_code}' "${LOCAL_API}/api/health")
[ "$HEALTH" = "200" ] || fail "health status=${HEALTH}"
pass "/api/health 200"

HIST=$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_URL}/history")
[ "$HIST" = "200" ] || fail "history page status=${HIST}"
pass "/history page 200"

ACC=$(curl -sS -o /tmp/phase42d_acc.json -w '%{http_code}' "${LOCAL_API}/api/accuracy/summary")
[ "$ACC" = "200" ] || fail "accuracy summary status=${ACC}"
pass "/api/accuracy/summary 200"

PERF=$(curl -sS -o /tmp/phase42d_perf.json -w '%{http_code}' "${LOCAL_API}/api/performance/summary")
[ "$PERF" = "200" ] || fail "performance summary status=${PERF}"
python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/phase42d_perf.json").read_text())
assert p.get("status") == "ok"
assert "markets" in p
assert "overall_accuracy" in p
print("performance_evaluated=", p.get("total_evaluated"))
PY
pass "/api/performance/summary 200"

TIPS=$(curl -sS -o /tmp/phase42d_tips.json -w '%{http_code}' "${LOCAL_API}/api/best-tips")
[ "$TIPS" = "200" ] || fail "best-tips status=${TIPS}"
python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/phase42d_tips.json").read_text())
assert p.get("status") == "ok"
assert "tips" in p
print("best_tips_count=", len(p.get("tips") or []))
PY
pass "/api/best-tips 200"

HIST_API=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/history?scope=all")
[ "$HIST_API" = "401" ] || [ "$HIST_API" = "403" ] || fail "history scope=all not protected status=${HIST_API}"
pass "history scope=all requires auth ${HIST_API}"

GLOBAL_API=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/history?scope=global")
[ "$GLOBAL_API" = "401" ] || [ "$GLOBAL_API" = "403" ] || fail "history scope=global not protected status=${GLOBAL_API}"
pass "history scope=global requires auth ${GLOBAL_API}"

LOGIN=$(curl -sS -o /tmp/phase42d_login.json -w '%{http_code}' \
  -X POST "${LOCAL_API}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"nonexistent-smoke@test.local","password":"wrong"}')
[ "$LOGIN" = "401" ] || [ "$LOGIN" = "400" ] || [ "$LOGIN" = "422" ] || fail "login endpoint changed status=${LOGIN}"
pass "login endpoint responds ${LOGIN}"

PRED=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/predict/999999999")
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
  if grep -qE 'fetchHistoryArchive|Global Archive|scope=all' "$BUNDLE_PATH" 2>/dev/null; then
    pass "frontend bundle references global archive"
  else
    fail "frontend bundle missing global archive references"
  fi
  if grep -qE 'fetchPerformanceSummary|fetchBestTips|Performance Center' "$BUNDLE_PATH" 2>/dev/null; then
    pass "frontend bundle references performance center"
  else
    fail "frontend bundle missing performance center references"
  fi
fi

echo "SMOKE_ALL_PASS"
