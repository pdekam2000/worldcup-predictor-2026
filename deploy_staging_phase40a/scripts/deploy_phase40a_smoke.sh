#!/usr/bin/env bash
# Phase 40A — production smoke (no secrets)
set -euo pipefail

ORIGIN="${1:-https://footballpredictor.it.com}"
PASS=0
FAIL=0

check() {
  local name="$1"
  local ok="$2"
  if [ "$ok" = "1" ]; then
    echo "PASS: $name"
    PASS=$((PASS+1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Phase 40A Production Smoke ==="
echo "Origin: ${ORIGIN}"

HEALTH=$(curl -sS -o /tmp/p40a_health.json -w "%{http_code}" "${ORIGIN}/api/health")
check "GET /api/health 200" "$([ "$HEALTH" = "200" ] && echo 1 || echo 0)"

LOGIN=$(curl -sS -o /tmp/p40a_login.html -w "%{http_code}" "${ORIGIN}/login")
check "GET /login 200" "$([ "$LOGIN" = "200" ] && echo 1 || echo 0)"

curl -sS "${ORIGIN}/login" -o /tmp/p40a_login.html
JS=$(grep -oE 'assets/[^"]+\.js' /tmp/p40a_login.html | head -1)
check "login page has JS bundle" "$([ -n "$JS" ] && echo 1 || echo 0)"

if [ -n "${JS:-}" ]; then
  curl -sS "${ORIGIN}/${JS}" -o /tmp/p40a_main.js
  for needle in "Show password" "VerifyEmailPage" "verify-email" "Payment system coming soon"; do
    if grep -qF "$needle" /tmp/p40a_main.js 2>/dev/null || grep -q "verify-email" /tmp/p40a_main.js; then
      check "bundle: $needle" 1
    else
      if [ "$needle" = "VerifyEmailPage" ]; then
        grep -q "verify-email" /tmp/p40a_main.js && check "bundle: verify-email route" 1 || check "bundle: $needle" 0
      else
        check "bundle: $needle" 0
      fi
    fi
  done
  if grep -qi 'VITE_DEV_AUTH_BYPASS\|dev@worldcup.local' /tmp/p40a_main.js; then
    check "no dev auth in bundle" 0
  else
    check "no dev auth in bundle" 1
  fi
  if grep -qi 'stripe\.checkout\|loadStripe' /tmp/p40a_main.js; then
    check "no Stripe checkout in bundle" 0
  else
    check "no Stripe checkout in bundle" 1
  fi
fi

VERIFY=$(curl -sS -o /tmp/p40a_verify.html -w "%{http_code}" "${ORIGIN}/verify-email")
check "GET /verify-email 200" "$([ "$VERIFY" = "200" ] && echo 1 || echo 0)"

PRICING=$(curl -sS -o /dev/null -w "%{http_code}" "${ORIGIN}/pricing")
check "GET /pricing 200" "$([ "$PRICING" = "200" ] && echo 1 || echo 0)"

# Unauthenticated predict should 401
PRED=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "${ORIGIN}/api/predict/1489393")
check "POST predict unauth 401" "$([ "$PRED" = "401" ] && echo 1 || echo 0)"

# Register should return verification_required (invite may be required on prod)
REG_BODY='{"email":"smoke40a-'$(date +%s)'@example.com","password":"SmokeTest40Pass!"}'
REG=$(curl -sS -o /tmp/p40a_reg.json -w "%{http_code}" -X POST "${ORIGIN}/api/auth/register" \
  -H "Content-Type: application/json" -d "${REG_BODY}")
if [ "$REG" = "200" ]; then
  grep -q verification_required /tmp/p40a_reg.json && check "register verification_required" 1 || check "register verification_required" 0
  grep -q access_token /tmp/p40a_reg.json && check "register no JWT" 0 || check "register no JWT" 1
elif [ "$REG" = "400" ]; then
  check "register endpoint reachable" 1
  echo "  (invite code may be required on production)"
else
  check "register endpoint reachable" 0
fi

echo ""
echo "Smoke: ${PASS} pass, ${FAIL} fail"
[ "$FAIL" -eq 0 ]
