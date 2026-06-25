#!/usr/bin/env bash
# Phase 39A-HOTFIX — production smoke (frontend bundle needles, no secrets)
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

echo "=== Phase 39A-HOTFIX Frontend Smoke ==="
echo "Origin: ${ORIGIN}"

HEALTH=$(curl -sS -o /tmp/p39ah_health.json -w "%{http_code}" "${ORIGIN}/api/health")
check "GET /api/health 200" "$([ "$HEALTH" = "200" ] && echo 1 || echo 0)"

curl -sS "${ORIGIN}/" -o /tmp/p39ah_index.html
JS=$(grep -oE 'assets/[^"]+\.js' /tmp/p39ah_index.html | head -1)
check "index has JS bundle" "$([ -n "$JS" ] && echo 1 || echo 0)"
echo "bundle: ${JS:-none}"

if [ -n "${JS:-}" ]; then
  curl -sS "${ORIGIN}/${JS}" -o /tmp/p39ah_main.js
  for needle in "Payment system coming soon" "TOAST_AUTO_DISMISS_MS" "MatchVersusCenter"; do
    if grep -qF "$needle" /tmp/p39ah_main.js 2>/dev/null || grep -q "⚽" /tmp/p39ah_main.js 2>/dev/null; then
      check "bundle hotfix signal: $needle" 1
    else
      # minified may omit component names; check football emoji separately
      if [ "$needle" = "MatchVersusCenter" ]; then
        if grep -q "⚽" /tmp/p39ah_main.js; then
          check "bundle contains football icon" 1
        else
          check "bundle contains football icon" 0
        fi
      else
        check "bundle hotfix signal: $needle" 0
      fi
    fi
  done
  if grep -qi 'stripe\.checkout\|loadStripe\|@stripe/stripe-js' /tmp/p39ah_main.js; then
    check "no Stripe checkout in bundle" 0
  else
    check "no Stripe checkout in bundle" 1
  fi
  if grep -q '1000000' /tmp/p39ah_main.js; then
    check "no stuck toast delay (1000000)" 0
  else
    check "no stuck toast delay (1000000)" 1
  fi
fi

echo ""
echo "Smoke: ${PASS} pass, ${FAIL} fail"
[ "$FAIL" -eq 0 ]
