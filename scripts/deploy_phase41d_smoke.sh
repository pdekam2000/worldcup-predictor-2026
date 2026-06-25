#!/usr/bin/env bash
# Phase 41D — production smoke: change password flow (creates ephemeral test user)
set -euo pipefail

APP=/opt/worldcup-predictor
BASE_URL="${BASE_URL:-https://footballpredictor.it.com}"
LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"

fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Phase 41D smoke ==="

HEALTH=$(curl -sS -o /tmp/phase41d_health.json -w '%{http_code}' "${LOCAL_API}/api/health")
[ "$HEALTH" = "200" ] || fail "health status=${HEALTH}"
pass "/api/health 200"

# Ephemeral user via Python on server DB
read -r TEST_EMAIL OLD_PWD NEW_PWD <<< "$(sudo -u www-data env PYTHONPATH="${APP}" bash -lc "
cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
import uuid
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.database.saas_factory import saas_uow

email = f'phase41d-smoke-{uuid.uuid4().hex[:8]}@test.local'
old_pwd = 'Phase41D-Smoke-Old!'
new_pwd = 'Phase41D-Smoke-New!'
with saas_uow() as uow:
    uow.users.create(email=email, password_hash=hash_password(old_pwd), email_verified=True)
print(email, old_pwd, new_pwd)
PY
")"

echo "smoke_user=${TEST_EMAIL}"

LOGIN=$(curl -sS -o /tmp/phase41d_login.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${TEST_EMAIL}\",\"password\":\"${OLD_PWD}\"}" \
  "${LOCAL_API}/api/auth/login")
[ "$LOGIN" = "200" ] || fail "login status=${LOGIN}"
TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/phase41d_login.json')).get('access_token',''))")
[ -n "$TOKEN" ] || fail "login missing jwt"
pass "login 200 + jwt"

SETTINGS=$(curl -sS -o /tmp/phase41d_settings.json -w '%{http_code}' \
  -H "Authorization: Bearer ${TOKEN}" \
  "${LOCAL_API}/api/user/settings")
[ "$SETTINGS" = "200" ] || fail "settings api status=${SETTINGS}"
pass "settings api 200"

FRONT=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE_URL}/settings")
[ "$FRONT" = "200" ] || fail "settings page status=${FRONT}"
pass "settings page 200"

WRONG=$(curl -sS -o /tmp/phase41d_wrong.json -w '%{http_code}' \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d "{\"current_password\":\"wrong-password\",\"new_password\":\"${NEW_PWD}\",\"confirm_password\":\"${NEW_PWD}\"}" \
  "${LOCAL_API}/api/auth/change-password")
[ "$WRONG" = "400" ] || fail "wrong current status=${WRONG}"
CODE=$(python3 -c "import json; d=json.load(open('/tmp/phase41d_wrong.json')).get('detail',{}); print(d.get('code','') if isinstance(d,dict) else '')")
[ "$CODE" = "current_password_invalid" ] || fail "wrong current code=${CODE}"
pass "wrong current password 400 current_password_invalid"

OK=$(curl -sS -o /tmp/phase41d_change.json -w '%{http_code}' \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d "{\"current_password\":\"${OLD_PWD}\",\"new_password\":\"${NEW_PWD}\",\"confirm_password\":\"${NEW_PWD}\"}" \
  "${LOCAL_API}/api/auth/change-password")
[ "$OK" = "200" ] || fail "change password status=${OK}"
CHANGED=$(python3 -c "import json; print(json.load(open('/tmp/phase41d_change.json')).get('password_changed'))")
[ "$CHANGED" = "True" ] || fail "password_changed not true"
pass "change password 200 password_changed=true"

ME=$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${TOKEN}" \
  "${LOCAL_API}/api/auth/me")
[ "$ME" = "401" ] || fail "old token still valid status=${ME}"
pass "old jwt invalidated 401"

LOGIN_NEW=$(curl -sS -o /tmp/phase41d_login_new.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${TEST_EMAIL}\",\"password\":\"${NEW_PWD}\"}" \
  "${LOCAL_API}/api/auth/login")
[ "$LOGIN_NEW" = "200" ] || fail "login new password status=${LOGIN_NEW}"
pass "login with new password 200"

# Cleanup test user (non-fatal)
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "
cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<PY || true
from sqlalchemy import delete, select
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.database.postgres.models import User, UserSettings
email = '${TEST_EMAIL}'
with saas_uow() as uow:
    row = uow.session.scalar(select(User).where(User.email == email))
    if row:
        uow.session.execute(delete(UserSettings).where(UserSettings.user_id == row.id))
        uow.session.delete(row)
        uow.session.flush()
print('cleanup_ok')
PY
" >/dev/null 2>&1 || true

echo "SMOKE_ALL_PASS"
