#!/usr/bin/env bash
# Phase 39B-5 — production smoke (no secrets printed)
set -euo pipefail

APP=/opt/worldcup-predictor
BASE="http://127.0.0.1:8000"

echo "=== Phase 39B-5 Live Smoke (server-local) ==="

check() {
  local name="$1"
  local ok="$2"
  if [ "$ok" = "1" ]; then echo "[PASS] $name"; else echo "[FAIL] $name"; fi
}

# Stripe env readiness
AUDIT=$(
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/audit_stripe_production_env.py" 2>&1 || true
)
echo "$AUDIT" | grep -E '^(STRIPE_|checkout_|portal_|webhook_|stripe_production_ready)' || true
READY=$(echo "$AUDIT" | grep '^stripe_production_ready:' | awk '{print $2}' || echo "false")
check "stripe_env_production_ready" "$([ "$READY" = "True" ] || [ "$READY" = "true" ] && echo 1 || echo 0)"

# Billing router mounted
MAIN=$(grep -c billing_router "${APP}/worldcup_predictor/api/main.py" 2>/dev/null || echo 0)
check "billing_router_in_main" "$([ "$MAIN" -ge 1 ] && echo 1 || echo 0)"

# Webhook rejects invalid signature
WH=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE}/api/billing/webhook" \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: t=0,v1=invalid" \
  -d '{"id":"evt_smoke","type":"ping"}' 2>/dev/null || echo "000")
check "webhook_invalid_signature_400" "$([ "$WH" = "400" ] && echo 1 || echo 0)"

# Frontend bundle — no secret keys
DIST=$(ls "${APP}/../var/www/worldcup/frontend/dist/assets/"*.js 2>/dev/null | head -1)
if [ -z "$DIST" ]; then DIST=$(ls /var/www/worldcup/frontend/dist/assets/*.js 2>/dev/null | head -1); fi
if [ -n "$DIST" ]; then
  if grep -qE 'sk_test_|sk_live_|whsec_' "$DIST" 2>/dev/null; then
    check "frontend_no_stripe_secrets" 0
  else
    check "frontend_no_stripe_secrets" 1
  fi
  if grep -qE 'billing/success|fetchBillingStatus|createCheckoutSession' "$DIST" 2>/dev/null; then
    check "frontend_billing_ui_present" 1
  else
    check "frontend_billing_ui_present" 0
  fi
else
  check "frontend_bundle_found" 0
fi

# Public health
PUB=$(curl -sf -o /dev/null -w "%{http_code}" https://footballpredictor.it.com/api/health 2>/dev/null || echo "000")
check "public_health_200" "$([ "$PUB" = "200" ] && echo 1 || echo 0)"

echo "=== End smoke (full checkout flow requires Stripe Dashboard keys + manual test card) ==="
