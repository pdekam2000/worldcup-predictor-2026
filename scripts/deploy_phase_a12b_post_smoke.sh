#!/usr/bin/env bash
# Phase A12B — post-deploy smoke (must all pass)
set -eu

BASE="${1:-https://footballpredictor.it.com}"
LOCAL="${2:-http://127.0.0.1:8000}"
fail=0
check() {
  local name="$1" url="$2" expect="$3"
  code=$(curl -s -o /tmp/a12b_body.txt -w "%{http_code}" "$url" || true)
  if echo "$expect" | grep -q "$code"; then
    echo "  [PASS] $name — http=$code"
  else
    echo "  [FAIL] $name — http=$code expected=$expect"
    head -c 120 /tmp/a12b_body.txt 2>/dev/null; echo
    fail=1
  fi
}

echo "=== A12B Post-Deploy Smoke (public) ==="
check "archive_page" "${BASE}/archive" "200"
check "accuracy_page" "${BASE}/accuracy" "200"
check "performance_summary" "${BASE}/api/performance/summary" "200"
check "performance_details" "${BASE}/api/performance/details" "200"
check "history_auth" "${BASE}/api/history" "401"
check "history_global_auth" "${BASE}/api/history/global" "401|404|422"

echo "=== A12B Post-Deploy Smoke (localhost API) ==="
check "local_health" "${LOCAL}/api/health" "200"
check "local_performance_summary" "${LOCAL}/api/performance/summary" "200"
check "local_performance_details" "${LOCAL}/api/performance/details" "200"
check "local_history" "${LOCAL}/api/history" "401"

if [ "$fail" -ne 0 ]; then
  echo "POST_DEPLOY_SMOKE=FAIL"
  exit 1
fi
echo "POST_DEPLOY_SMOKE=PASS"
exit 0
