#!/usr/bin/env bash
set -euo pipefail
BASE="${PHASE63_BASE_URL:-https://footballpredictor.it.com}"
check() {
  local path="$1"; shift
  local codes=("$@")
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}${path}" || echo "000")
  for c in "${codes[@]}"; do [ "${code}" = "${c}" ] && { echo "PASS ${path} -> ${code}"; return 0; }; done
  echo "FAIL ${path} -> ${code} (expected ${codes[*]})"; return 1
}
echo "Smoke: ${BASE}"
check "/" 200
check "/owner-login" 200
check "/owner" 200 302
check "/owner/autonomous" 200 302
check "/api/health" 200
check "/api/owner/overview" 401 403
check "/api/owner/autonomous/status" 401 403
check "/api/owner/monitoring" 401 403
check "/api/admin/elite-shadow/predictions" 401 403
echo "SMOKE_OK"
