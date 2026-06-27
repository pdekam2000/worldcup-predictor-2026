#!/usr/bin/env bash
# HOTFIX — Premium plan 404 — post-deploy smoke
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"

echo "=== Hotfix premium plan 404 smoke ==="

for path in \
  /api/billing/checkout \
  /api/subscription/checkout \
  /api/stripe/create-checkout-session; do
  code=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE}${path}" || echo "000")
  echo "${path}: ${code}"
  test "${code}" = "200"
done

code=$(curl -sf -o /dev/null -w "%{http_code}" -X POST "${BASE}/api/billing/create-checkout-session" \
  -H "Content-Type: application/json" -d '{"plan":"starter"}' || echo "000")
echo "POST /api/billing/create-checkout-session (unauth): ${code}"
test "${code}" = "401"

curl -sf "${BASE}/api/health" >/dev/null
echo "health: ok"
echo "SMOKE_OK"
