#!/usr/bin/env bash
# Phase 44E Stripe activation smoke tests
set -euo pipefail

APP=/opt/worldcup-predictor
cd "${APP}"
set -a && source .env.production && set +a

FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Phase 44E smoke ==="

HTTPH=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/health")
[ "${HTTPH}" = "200" ] && pass "/api/health 200" || fail "/api/health ${HTTPH}"

READINESS=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -c \"
from worldcup_predictor.billing.billing_service import BillingService
from worldcup_predictor.config.settings import get_settings
r = BillingService(settings=get_settings()).readiness()
print('checkout_enabled=' + str(r.checkout_enabled))
print('portal_enabled=' + str(r.portal_enabled))
\"")

echo "${READINESS}"
echo "${READINESS}" | grep -q "checkout_enabled=True" && pass "checkout_enabled" || fail "checkout_disabled"
echo "${READINESS}" | grep -q "portal_enabled=True" && pass "portal_enabled" || fail "portal_disabled"

# Legacy billing routes
for path in /api/billing/checkout /api/subscription/checkout; do
  HTTPL=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000${path}")
  [ "${HTTPL}" = "200" ] && pass "${path} 200" || fail "${path} ${HTTPL}"
done

# Create checkout session for ephemeral test user
CHECKOUT=$(sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -c \"
import uuid
from fastapi.testclient import TestClient
from worldcup_predictor.api.main import app
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.auth.auth_rate_limit import reset_auth_rate_limits
from worldcup_predictor.database.saas_factory import saas_uow, postgres_configured
if not postgres_configured():
    print('SKIP_NO_PG')
    raise SystemExit(0)
reset_auth_rate_limits()
email = f'smoke44e-{uuid.uuid4().hex[:8]}@test.local'
pwd = 'Smoke44E-Pass1!'
with saas_uow() as uow:
    uow.users.create(email=email, password_hash=hash_password(pwd), email_verified=True)
client = TestClient(app)
login = client.post('/api/auth/login', json={'email': email, 'password': pwd})
token = login.json().get('access_token')
headers = {'Authorization': f'Bearer {token}'}
ready = client.get('/api/billing/readiness', headers=headers)
starter = client.post('/api/billing/create-checkout-session', headers=headers, json={'plan': 'starter'})
print('ready_checkout=' + str(ready.json().get('checkout_enabled')))
print('starter_status=' + str(starter.status_code))
print('has_url=' + str(bool(starter.json().get('checkout_url'))))
\"" 2>&1) || true

echo "${CHECKOUT}"
if echo "${CHECKOUT}" | grep -q "SKIP_NO_PG"; then
  pass "checkout_session_skipped_no_pg"
elif echo "${CHECKOUT}" | grep -q "starter_status=200" && echo "${CHECKOUT}" | grep -q "has_url=True"; then
  pass "starter_checkout_session"
else
  fail "starter_checkout_session"
fi

HTTPP=$(curl -sS -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/performance/summary")
[ "${HTTPP}" = "200" ] && pass "/api/performance/summary 200" || fail "performance ${HTTPP}"

HTTPF=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/subscription" 2>/dev/null || echo "000")
[ "${HTTPF}" = "200" ] && pass "/subscription page 200" || fail "/subscription ${HTTPF}"

systemctl is-active worldcup-evaluate-results.timer >/dev/null 2>&1 && pass "eval_timer" || fail "eval_timer"

if [ "${FAIL}" -eq 0 ]; then echo SMOKE_ALL_PASS; else exit 1; fi
