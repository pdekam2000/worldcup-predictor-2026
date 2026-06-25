#!/usr/bin/env bash
# Phase 60A production smoke — full GUI + shadow comparison
set -euo pipefail

APP=/opt/worldcup-predictor
FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 60A smoke ==="

HTTP_HEALTH=$(curl -sS -o /tmp/phase60a_health.json -w "%{http_code}" "http://127.0.0.1:8000/api/health")
[ "${HTTP_HEALTH}" = "200" ] && pass "/api/health 200" || fail "/api/health ${HTTP_HEALTH}"

HTTP_UNAUTH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/admin/elite-shadow/summary")
[ "${HTTP_UNAUTH}" = "401" ] && pass "elite-shadow summary unauth 401" || fail "elite-shadow summary unauth ${HTTP_UNAUTH}"

HTTP_COMP_UNAUTH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/admin/elite-shadow/comparison")
[ "${HTTP_COMP_UNAUTH}" = "401" ] && pass "elite-shadow comparison unauth 401" || fail "elite-shadow comparison unauth ${HTTP_COMP_UNAUTH}"

HTTP_GT=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/goal-timing/dashboard")
[ "${HTTP_GT}" = "200" ] && pass "public goal-timing 200" || fail "goal-timing ${HTTP_GT}"

if sudo -u www-data test -r "${APP}/data/shadow/elite_orchestrator_predictions.jsonl"; then
  pass "shadow predictions JSONL readable"
else
  fail "shadow predictions JSONL missing"
fi

HTTP_FE=$(curl -sS -o /tmp/phase60a_fe.html -w "%{http_code}" "https://footballpredictor.it.com/admin/elite-shadow" 2>/dev/null || echo "000")
[ "${HTTP_FE}" = "200" ] && pass "/admin/elite-shadow SPA 200" || fail "/admin/elite-shadow SPA ${HTTP_FE}"

if grep -rq "Shadow vs Production" "${APP}/base44-d/dist" 2>/dev/null || grep -q "Shadow vs Production" /tmp/phase60a_fe.html 2>/dev/null; then
  pass "comparison section marker in build"
else
  fail "comparison section marker missing"
fi

if grep -rq "Elite Shadow Preview" "${APP}/base44-d/dist" 2>/dev/null || grep -q "Elite Shadow Preview" /tmp/phase60a_fe.html 2>/dev/null; then
  pass "elite shadow preview marker"
else
  fail "elite shadow preview marker missing"
fi

HTTP_HOME=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/" 2>/dev/null || echo "000")
[ "${HTTP_HOME}" = "200" ] && pass "homepage 200" || fail "homepage ${HTTP_HOME}"

# Backend route registered
if sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && .venv/bin/python -c 'from worldcup_predictor.api.routes.admin_elite_shadow import router; assert any(\"comparison\" in getattr(r,\"path\",\"\") for r in router.routes); print(\"comparison_route_ok\")'" \
  2>/dev/null | grep -q comparison_route_ok; then
  pass "comparison API route registered"
else
  fail "comparison API route missing"
fi

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase60a_full_deploy.py --smoke-only" \
  2>&1 | tee /tmp/phase60a_validate_smoke.log | tail -25

if grep -q "SMOKE_ALL_PASS" /tmp/phase60a_validate_smoke.log 2>/dev/null; then
  pass "validate_phase60a smoke"
else
  fail "validate_phase60a smoke"
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
