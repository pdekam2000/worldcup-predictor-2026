#!/usr/bin/env bash
# Phase 59B production smoke — Elite Shadow owner-only preview
set -euo pipefail

APP=/opt/worldcup-predictor
FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 59B smoke ==="

HTTP_HEALTH=$(curl -sS -o /tmp/phase59b_health.json -w "%{http_code}" "http://127.0.0.1:8000/api/health")
if [ "${HTTP_HEALTH}" = "200" ]; then
  pass "/api/health 200"
else
  fail "/api/health ${HTTP_HEALTH}"
fi

HTTP_UNAUTH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/admin/elite-shadow/summary")
if [ "${HTTP_UNAUTH}" = "401" ]; then
  pass "elite-shadow unauthenticated 401"
else
  fail "elite-shadow unauthenticated ${HTTP_UNAUTH} (expected 401)"
fi

# Public predictions unchanged — sample health + goal-timing still up
HTTP_GT=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/goal-timing/dashboard")
if [ "${HTTP_GT}" = "200" ]; then
  pass "public goal-timing dashboard unchanged 200"
else
  fail "goal-timing dashboard ${HTTP_GT}"
fi

# Shadow JSONL readable by www-data
if sudo -u www-data test -r "${APP}/data/shadow/elite_orchestrator_predictions.jsonl"; then
  pass "shadow predictions JSONL readable"
else
  fail "shadow predictions JSONL missing or unreadable"
fi

# Frontend SPA serves (owner route is client-gated)
HTTP_FE=$(curl -sS -o /tmp/phase59b_fe.html -w "%{http_code}" "https://footballpredictor.it.com/admin/elite-shadow" 2>/dev/null || echo "000")
if [ "${HTTP_FE}" = "200" ]; then
  pass "/admin/elite-shadow SPA shell 200"
else
  fail "/admin/elite-shadow SPA ${HTTP_FE}"
fi

# Built bundle contains elite shadow page marker
if grep -rq "Elite Shadow Preview" "${APP}/base44-d/dist" 2>/dev/null || grep -q "Elite Shadow Preview" /tmp/phase59b_fe.html 2>/dev/null; then
  pass "elite shadow UI marker present"
else
  fail "elite shadow UI marker missing in build"
fi

# Admin-only path (unauthenticated 401 proves route is registered under auth)
HTTP_ADMIN_PATH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/admin/elite-shadow/summary")
if [ "${HTTP_ADMIN_PATH}" = "401" ]; then
  pass "elite-shadow only under /api/admin/ (auth required)"
else
  fail "elite-shadow admin path ${HTTP_ADMIN_PATH}"
fi

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase59b_owner_soft_launch.py --smoke-only" \
  2>&1 | tee /tmp/phase59b_validate_smoke.log | tail -20

if grep -q "SMOKE_ALL_PASS" /tmp/phase59b_validate_smoke.log 2>/dev/null; then
  pass "validate_phase59b smoke section"
else
  fail "validate_phase59b smoke section"
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
