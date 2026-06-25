#!/usr/bin/env bash
# Phase 44 hardening production smoke
set -euo pipefail

APP=/opt/worldcup-predictor
cd "${APP}"
set -a && source .env.production && set +a

FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 44 hardening smoke ==="

HTTPH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/health")
[ "${HTTPH}" = "200" ] && pass "/api/health 200" || fail "/api/health ${HTTPH}"

HTTPP=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/performance/summary")
[ "${HTTPP}" = "200" ] && pass "/api/performance/summary 200" || fail "/api/performance/summary ${HTTPP}"

HTTPB=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/best-tips")
[ "${HTTPB}" = "200" ] && pass "/api/best-tips 200" || fail "/api/best-tips ${HTTPB}"

systemctl is-enabled worldcup-evaluate-results.timer >/dev/null 2>&1 && pass "eval timer enabled" || fail "eval timer missing"
systemctl is-active worldcup-evaluate-results.timer >/dev/null 2>&1 && pass "eval timer active" || fail "eval timer inactive"

for path in history subscription login register; do
  HTTPF=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/${path}" 2>/dev/null || echo "000")
  [ "${HTTPF}" = "200" ] && pass "/${path} page 200" || fail "/${path} page ${HTTPF}"
done

# Billing legacy routes must not 404
for path in /api/billing/checkout /api/subscription/checkout /api/stripe/create-checkout-session; do
  HTTPL=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000${path}")
  [ "${HTTPL}" = "200" ] && pass "${path} legacy 200" || fail "${path} legacy ${HTTPL}"
done

# Safe enrichment logger deployed
if [ -f worldcup_predictor/providers/safe_enrichment_logger.py ]; then
  pass "safe_enrichment_logger present"
else
  fail "safe_enrichment_logger missing"
fi

if grep -q "log_enrichment_failure" worldcup_predictor/orchestration/predict_pipeline.py 2>/dev/null; then
  pass "predict_pipeline uses structured enrichment logging"
else
  fail "predict_pipeline missing enrichment logger"
fi

if grep -E "except Exception:\s*$" -A1 worldcup_predictor/orchestration/predict_pipeline.py 2>/dev/null | grep -q "pass"; then
  fail "silent pass still in predict_pipeline"
else
  pass "no silent pass in predict_pipeline"
fi

if [ -f STORAGE_CONTRACT.md ]; then
  pass "storage contract doc present"
else
  fail "storage contract doc missing"
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
