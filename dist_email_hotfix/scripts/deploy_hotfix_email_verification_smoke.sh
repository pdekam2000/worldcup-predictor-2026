#!/usr/bin/env bash
# HOTFIX — Email verification register — post-deploy smoke
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"

echo "=== Hotfix email verification smoke ==="

curl -sf "${BASE}/api/health" >/dev/null
echo "health: ok"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE}/api/auth/resend-verification-email" \
  -H "Content-Type: application/json" -d '{"email":"smoke-missing@example.com"}')
echo "POST /api/auth/resend-verification-email: ${code}"
test "${code}" = "200"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE}/api/auth/resend-verification" \
  -H "Content-Type: application/json" -d '{"email":"smoke-missing@example.com"}')
echo "POST /api/auth/resend-verification: ${code}"
test "${code}" = "200"

echo "SMOKE_OK"
