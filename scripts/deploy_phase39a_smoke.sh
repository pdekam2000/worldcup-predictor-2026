#!/usr/bin/env bash
# Phase 39A — production frontend smoke (bundle needles, no secrets)
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

echo "=== Phase 39A Frontend Smoke ==="
echo "Origin: ${ORIGIN}"

HEALTH=$(curl -sS -o /tmp/p39a_health.json -w "%{http_code}" "${ORIGIN}/api/health")
check "GET /api/health 200" "$([ "$HEALTH" = "200" ] && echo 1 || echo 0)"

PRICING=$(curl -sS -o /tmp/p39a_pricing.html -w "%{http_code}" "${ORIGIN}/pricing")
check "GET /pricing 200" "$([ "$PRICING" = "200" ] && echo 1 || echo 0)"

curl -sS "${ORIGIN}/pricing" -o /tmp/p39a_pricing.html
JS=$(grep -oE 'assets/[^"]+\.js' /tmp/p39a_pricing.html | head -1)
check "pricing page has JS bundle" "$([ -n "$JS" ] && echo 1 || echo 0)"
echo "bundle: ${JS:-none}"

if [ -n "${JS:-}" ]; then
  curl -sS "${ORIGIN}/${JS}" -o /tmp/p39a_main.js
  for needle in "Payment system coming soon" "Message Admin" "Compare plans" "28 predictions" "Recommended" "/api/admin/commercial/analytics"; do
    if grep -qF "$needle" /tmp/p39a_main.js; then
      check "bundle contains: $needle" 1
    else
      check "bundle contains: $needle" 0
    fi
  done
  if grep -qi 'stripe\.checkout\|loadStripe\|@stripe/stripe-js' /tmp/p39a_main.js; then
    check "no Stripe checkout in bundle" 0
  else
    check "no Stripe checkout in bundle" 1
  fi
  if grep -q 'ADMIN_CONTACT_EMAIL' /tmp/p39a_main.js; then
    check "admin email hidden from bundle" 0
  else
    check "admin email hidden from bundle" 1
  fi
fi

echo ""
echo "Smoke: ${PASS} pass, ${FAIL} fail"
[ "$FAIL" -eq 0 ]
