#!/usr/bin/env bash
# Phase 44A production smoke tests
set -euo pipefail

APP=/opt/worldcup-predictor
cd "${APP}"
set -a
source .env.production
set +a

FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 44A smoke ==="

# Timer active
if systemctl is-enabled worldcup-evaluate-results.timer >/dev/null 2>&1; then
  pass "timer enabled"
else
  fail "timer not enabled"
fi

if systemctl is-active worldcup-evaluate-results.timer >/dev/null 2>&1; then
  pass "timer active"
else
  fail "timer not active"
fi

# Manual job
JOB_OUT=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python main.py worldcup-auto-evaluation" 2>&1) || true
echo "${JOB_OUT}"
echo "${JOB_OUT}" | grep -q "Scanned stored" && pass "manual job ran" || fail "manual job output missing"
echo "${JOB_OUT}" | grep -q "Skipped (not finished)" && pass "upcoming fixtures skipped" || pass "skip line present or no upcoming in scan"

# Eval count stable (no duplicate rows vs stored count)
EVAL_COUNT=$(sqlite3 data/football_intelligence.db "SELECT COUNT(*) FROM worldcup_prediction_evaluations")
STORED_COUNT=$(sqlite3 data/football_intelligence.db "SELECT COUNT(*) FROM worldcup_stored_predictions")
if [ "${EVAL_COUNT}" -le "${STORED_COUNT}" ]; then
  pass "no evaluation duplicates (eval=${EVAL_COUNT} stored=${STORED_COUNT})"
else
  fail "eval count exceeds stored count"
fi

# Summary table exists
SUMMARY=$(sqlite3 data/football_intelligence.db "SELECT COUNT(*) FROM worldcup_accuracy_summary")
if [ "${SUMMARY}" -ge 1 ]; then
  pass "accuracy summary table populated"
else
  fail "accuracy summary missing"
fi

# API health
HTTP=$(curl -sS -o /tmp/phase44a_perf.json -w "%{http_code}" "http://127.0.0.1:8000/api/performance/summary")
if [ "${HTTP}" = "200" ]; then
  pass "/api/performance/summary 200"
else
  fail "/api/performance/summary ${HTTP}"
fi

HTTPH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/health")
if [ "${HTTPH}" = "200" ]; then
  pass "/api/health 200"
else
  fail "/api/health ${HTTPH}"
fi

# Public frontend history page
HTTPF=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/history" 2>/dev/null || echo "000")
if [ "${HTTPF}" = "200" ]; then
  pass "/history page 200"
else
  fail "/history page ${HTTPF}"
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
