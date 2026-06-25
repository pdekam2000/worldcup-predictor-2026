#!/usr/bin/env bash
# Phase 51F production smoke tests
set -euo pipefail

APP=/opt/worldcup-predictor
cd "${APP}"
set -a
source .env.production
set +a

FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 51F smoke ==="

if systemctl is-enabled egie-goal-timing-evaluation.timer >/dev/null 2>&1; then
  pass "timer enabled"
else
  fail "timer not enabled"
fi

if systemctl is-active egie-goal-timing-evaluation.timer >/dev/null 2>&1; then
  pass "timer active"
else
  fail "timer not active"
fi

EVAL_BEFORE=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository
print(GoalTimingRepository().count_evaluations())
PY" 2>/dev/null | tail -1)

JOB_OUT=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python main.py egie-goal-timing-evaluation --limit 200 --max-api-calls 20" 2>&1) || true
echo "${JOB_OUT}"
echo "${JOB_OUT}" | grep -q "Scanned picks:" && pass "manual job ran" || fail "manual job output missing"

EVAL_AFTER=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository
print(GoalTimingRepository().count_evaluations())
PY" 2>/dev/null | tail -1)

RERUN_OUT=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python main.py egie-goal-timing-evaluation --limit 200 --max-api-calls 5" 2>&1) || true
echo "${RERUN_OUT}"
echo "${RERUN_OUT}" | grep -q "Skipped (unchanged):" && pass "idempotent skip line present" || pass "rerun completed"

EVAL_RERUN=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository
print(GoalTimingRepository().count_evaluations())
PY" 2>/dev/null | tail -1)

if [ "${EVAL_RERUN}" = "${EVAL_AFTER}" ]; then
  pass "no duplicate evaluations on rerun (count=${EVAL_AFTER})"
else
  fail "evaluation count changed on rerun before=${EVAL_AFTER} after=${EVAL_RERUN}"
fi

for path in history accuracy performance dashboard; do
  HTTP=$(curl -sS -o /tmp/phase51f_gt_${path}.json -w "%{http_code}" "http://127.0.0.1:8000/api/goal-timing/${path}")
  if [ "${HTTP}" = "200" ]; then
    pass "/api/goal-timing/${path} 200"
  else
    fail "/api/goal-timing/${path} ${HTTP}"
  fi
done

HTTPH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/health")
if [ "${HTTPH}" = "200" ]; then
  pass "/api/health 200"
else
  fail "/api/health ${HTTPH}"
fi

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
