#!/usr/bin/env bash
# Phase 42B production smoke
set -euo pipefail

LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-https://footballpredictor.it.com}"

fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Phase 42B smoke ==="

HEALTH=$(curl -sS -o /tmp/phase42b_health.json -w '%{http_code}' "${LOCAL_API}/api/health")
[ "$HEALTH" = "200" ] || fail "health status=${HEALTH}"
pass "/api/health 200"

SUMMARY=$(curl -sS -o /tmp/phase42b_summary.json -w '%{http_code}' "${LOCAL_API}/api/accuracy/summary")
[ "$SUMMARY" = "200" ] || fail "accuracy summary status=${SUMMARY}"
pass "/api/accuracy/summary 200"

python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/phase42b_summary.json").read_text())
assert p.get("status") == "ok"
assert "data_source" in p
assert p.get("data_source") not in {"mock", "dev_demo", "hardcoded"}
assert "73.2" not in json.dumps(p)
print("summary_data_source=", p.get("data_source"))
print("summary_settled=", (p.get("correct_predictions") or 0) + (p.get("wrong_predictions") or 0))
PY
pass "summary schema + no fake data"

ADMIN=$(curl -sS -o /dev/null -w '%{http_code}' "${LOCAL_API}/api/admin/accuracy/summary")
[ "$ADMIN" = "401" ] || [ "$ADMIN" = "403" ] || fail "admin exposed status=${ADMIN}"
pass "admin still protected ${ADMIN}"

PAGE=$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_URL}/accuracy")
[ "$PAGE" = "200" ] || fail "accuracy page status=${PAGE}"
pass "/accuracy page 200"

BUNDLE=$(python3 <<'PY'
import re
from pathlib import Path
html = Path("/var/www/worldcup/frontend/dist/index.html").read_text()
m = re.search(r'/assets/(index-[^"]+\.js)', html)
print(m.group(1) if m else "")
PY
)
BUNDLE="/var/www/worldcup/frontend/dist/assets/${BUNDLE}"
if [ -n "$BUNDLE" ] && [ -f "$BUNDLE" ]; then
  if grep -qE 'accuracy/summary|/api/accuracy' "$BUNDLE" 2>/dev/null; then
    pass "frontend bundle references accuracy API"
  else
    fail "frontend bundle missing accuracy API"
  fi
  if grep -q 'monthlyData' "$BUNDLE" 2>/dev/null; then
    fail "frontend still has monthlyData mock"
  else
    pass "no monthlyData mock in bundle"
  fi
fi

echo "SMOKE_ALL_PASS"
