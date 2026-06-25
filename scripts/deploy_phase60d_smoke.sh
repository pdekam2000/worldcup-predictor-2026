#!/usr/bin/env bash
# Phase 60D production smoke
set -euo pipefail

APP=/opt/worldcup-predictor
FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 60D smoke ==="

HTTP_HEALTH=$(curl -sS -o /tmp/phase60d_health.json -w "%{http_code}" "http://127.0.0.1:8000/api/health")
[ "${HTTP_HEALTH}" = "200" ] && pass "/api/health 200" || fail "/api/health ${HTTP_HEALTH}"

HTTP_GT=$(curl -sS -o /tmp/phase60d_gt.json -w "%{http_code}" "http://127.0.0.1:8000/api/goal-timing/dashboard")
[ "${HTTP_GT}" = "200" ] && pass "goal-timing dashboard 200" || fail "goal-timing dashboard ${HTTP_GT}"

HTTP_ELITE_UNAUTH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/elite/world-cup/predictions")
[ "${HTTP_ELITE_UNAUTH}" = "401" ] || [ "${HTTP_ELITE_UNAUTH}" = "403" ] && pass "elite wc unauth blocked ${HTTP_ELITE_UNAUTH}" || fail "elite wc unauth ${HTTP_ELITE_UNAUTH}"

HTTP_SHADOW_UNAUTH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/admin/elite-shadow/summary")
[ "${HTTP_SHADOW_UNAUTH}" = "401" ] && pass "elite-shadow summary unauth 401" || fail "elite-shadow summary unauth ${HTTP_SHADOW_UNAUTH}"

HTTP_RESEARCH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/research/highlights")
[ "${HTTP_RESEARCH}" = "200" ] && pass "research highlights 200" || fail "research highlights ${HTTP_RESEARCH}"

HTTP_HOME=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/" 2>/dev/null || echo "000")
[ "${HTTP_HOME}" = "200" ] && pass "homepage 200" || fail "homepage ${HTTP_HOME}"

HTTP_FE_ELITE=$(curl -sS -o /tmp/phase60d_elite_wc.html -w "%{http_code}" "https://footballpredictor.it.com/elite/world-cup" 2>/dev/null || echo "000")
[ "${HTTP_FE_ELITE}" = "200" ] && pass "/elite/world-cup SPA 200" || fail "/elite/world-cup SPA ${HTTP_FE_ELITE}"

HTTP_FE_SHADOW=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/admin/elite-shadow" 2>/dev/null || echo "000")
[ "${HTTP_FE_SHADOW}" = "200" ] && pass "/admin/elite-shadow SPA 200" || fail "/admin/elite-shadow SPA ${HTTP_FE_SHADOW}"

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && .venv/bin/python scripts/validate_phase60d_request_failed_and_elite_wc_page.py" \
  2>&1 | tee /tmp/phase60d_validate.log | tail -30

if grep -q "PHASE_60D_VALIDATION:" /tmp/phase60d_validate.log 2>/dev/null && ! grep -q "FAIL" /tmp/phase60d_validate.log 2>/dev/null; then
  pass "validate_phase60d"
else
  fail "validate_phase60d"
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
