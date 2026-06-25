#!/usr/bin/env bash
# Phase 62 production smoke
set -euo pipefail

BASE="${PHASE62_BASE_URL:-https://footballpredictor.it.com}"

check() {
  local path="$1"
  shift
  local codes=("$@")
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}${path}" || echo "000")
  local ok=0
  for c in "${codes[@]}"; do
    if [ "${code}" = "${c}" ]; then ok=1; break; fi
  done
  if [ "${ok}" -eq 1 ]; then
    echo "PASS ${path} -> ${code}"
  else
    echo "FAIL ${path} -> ${code} (expected ${codes[*]})"
    return 1
  fi
}

echo "Smoke base: ${BASE}"
check "/" 200
check "/login" 200
check "/owner-login" 200
check "/research/highlights" 200
check "/dashboard" 200 302 307
check "/matches" 200 302 307
check "/goal-timing/dashboard" 200 302 307
check "/elite/world-cup" 200 302 307
check "/admin/elite-shadow" 200 302 307
check "/subscription" 200 302 307
check "/settings" 200 302 307
check "/accuracy" 200 302 307
check "/api/health" 200
check "/api/research/highlights" 200
check "/api/goal-timing/dashboard" 200 503
check "/api/elite/world-cup/predictions" 401 403
check "/api/admin/elite-shadow/predictions" 401 403

echo "SMOKE_OK"
