#!/usr/bin/env bash
# Emergency owner login fix — production hotfix runner (no secrets in stdout).
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
FRONTEND="${FRONTEND:-/var/www/worldcup/frontend/dist}"
EMAIL="${EMAIL:-kamangar.pedram@gmail.com}"
PW_FILE="${PW_FILE:-/root/.wcp_phase41c_owner_login.txt}"

echo "=== Emergency Owner Login Fix ==="

if [[ ! -f "$PW_FILE" ]]; then
  openssl rand -base64 24 > "$PW_FILE"
  chmod 600 "$PW_FILE"
  echo "Created password file: $PW_FILE"
fi

export OWNER_LOGIN_PASSWORD
OWNER_LOGIN_PASSWORD="$(tr -d '\r\n' < "$PW_FILE")"

cd "$APP"

echo "=== 1. Ensure owner account ==="
sudo -u www-data env OWNER_LOGIN_PASSWORD="$OWNER_LOGIN_PASSWORD" PYTHONPATH="$APP" bash -lc \
  "cd $APP && set -a && source .env.production && set +a && .venv/bin/python scripts/ensure_owner_account.py --email $EMAIL"

echo "=== 2. Reset owner password (hash only) ==="
sudo -u www-data env OWNER_LOGIN_PASSWORD="$OWNER_LOGIN_PASSWORD" PYTHONPATH="$APP" bash -lc \
  "cd $APP && set -a && source .env.production && set +a && .venv/bin/python scripts/reset_owner_login_password.py --email $EMAIL --password-env OWNER_LOGIN_PASSWORD"

echo "=== 3. Frontend build ==="
cd "$APP/base44-d"
npm run build
rsync -a --delete dist/ "$FRONTEND/"
chown -R www-data:www-data "$FRONTEND"

echo "=== 4. Restart API ==="
systemctl restart worldcup-api
sleep 3

echo "=== 5. API smoke tests ==="
AUTH_CFG_CODE=$(curl -sS -o /tmp/emergency_auth_config.json -w '%{http_code}' \
  "https://footballpredictor.it.com/api/auth/config" || true)
echo "auth_config_http=$AUTH_CFG_CODE"

LOGIN_CODE=$(curl -sS -o /tmp/emergency_login.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${OWNER_LOGIN_PASSWORD}\"}" \
  "https://footballpredictor.it.com/api/auth/login" || true)
echo "login_http=$LOGIN_CODE"

if [[ "$LOGIN_CODE" == "200" ]]; then
  python3 - <<'PY'
import json
p=json.load(open("/tmp/emergency_login.json"))
u=p.get("user") or {}
print("login_role=" + str(u.get("role")))
print("has_token=" + str(bool(p.get("access_token"))))
PY
  TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/emergency_login.json')).get('access_token',''))")
  OWNER_CODE=$(curl -sS -o /tmp/emergency_owner.json -w '%{http_code}' \
    -H "Authorization: Bearer ${TOKEN}" \
    "https://footballpredictor.it.com/api/owner/overview" || true)
  echo "owner_overview_http=$OWNER_CODE"
else
  echo "login_failed"
fi

echo "=== 6. Login page bundle check ==="
grep -q 'Welcome back' "$FRONTEND/assets/"index-*.js 2>/dev/null && echo "login_strings_ok=yes" || echo "login_strings_ok=maybe_minified"

echo "=== DONE ==="
