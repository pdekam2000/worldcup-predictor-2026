#!/usr/bin/env bash
set -euo pipefail
BASE="${HOTFIX_BASE_URL:-https://footballpredictor.it.com}"
FIXTURE="${HOTFIX_FIXTURE_ID:-1489410}"
COMP="${HOTFIX_COMPETITION:-world_cup_2026}"

curl -fsS "${BASE}/api/health" >/dev/null && echo "OK health"
curl -fsS "${BASE}/matches" >/dev/null && echo "OK /matches"
curl -fsS "${BASE}/matches/${FIXTURE}?competition=${COMP}" >/dev/null && echo "OK match detail shell"
curl -fsS "${BASE}/combo-tips" >/dev/null && echo "OK combo-tips"
curl -fsS "${BASE}/betting-plan" >/dev/null && echo "OK betting-plan"
curl -fsS "${BASE}/paper-betting" >/dev/null && echo "OK paper-betting"
curl -fsS "${BASE}/public/accuracy" >/dev/null && echo "OK public accuracy"
curl -fsS -o /dev/null -w "predict=%{http_code}\n" "${BASE}/api/predict/${FIXTURE}?competition=${COMP}"
curl -fsS "${BASE}/api/predops/snapshots/latest?fixture_id=${FIXTURE}" | head -c 200 && echo
echo "SMOKE_DONE"
