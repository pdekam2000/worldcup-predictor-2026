#!/usr/bin/env bash
# Phase 51G production smoke — EGIE monitoring dashboard
set -euo pipefail

APP=/opt/worldcup-predictor
FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 51G smoke ==="

for path in dashboard picks history accuracy performance; do
  HTTP=$(curl -sS -o "/tmp/phase51g_${path}.json" -w "%{http_code}" "http://127.0.0.1:8000/api/goal-timing/${path}")
  if [ "${HTTP}" = "200" ]; then
    pass "/api/goal-timing/${path} 200"
  else
    fail "/api/goal-timing/${path} ${HTTP}"
  fi
done

HTTPF=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/goal-timing/dashboard" 2>/dev/null || echo "000")
if [ "${HTTPF}" = "200" ]; then
  pass "/goal-timing/dashboard page 200"
else
  fail "/goal-timing/dashboard page ${HTTPF}"
fi

PUB=$(python3 -c "import json; print(json.load(open('/tmp/phase51g_dashboard.json')).get('counts',{}).get('published_picks',0))" 2>/dev/null || echo 0)
EVAL=$(python3 -c "import json; print(json.load(open('/tmp/phase51g_dashboard.json')).get('counts',{}).get('evaluated_picks',0))" 2>/dev/null || echo 0)
if [ "${PUB}" -ge 48 ] 2>/dev/null; then
  pass "published picks >= 48 (${PUB})"
else
  fail "published picks ${PUB} (expected >= 48)"
fi
if [ "${EVAL}" -ge 1 ] 2>/dev/null; then
  pass "evaluated picks >= 1 (${EVAL})"
else
  fail "evaluated picks ${EVAL}"
fi

systemctl is-active egie-goal-timing-evaluation.timer >/dev/null 2>&1 && pass "scheduler timer active" || fail "scheduler inactive"

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
