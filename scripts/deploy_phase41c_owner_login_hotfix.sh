#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
EMAIL=kamangar.pedram@gmail.com
PW_FILE=/root/.wcp_phase41c_owner_login.txt

if [[ ! -f "$PW_FILE" ]]; then
  openssl rand -base64 24 > "$PW_FILE"
  chmod 600 "$PW_FILE"
fi

export OWNER_LOGIN_PASSWORD
OWNER_LOGIN_PASSWORD="$(tr -d '\r\n' < "$PW_FILE")"

sudo -u www-data env OWNER_LOGIN_PASSWORD="$OWNER_LOGIN_PASSWORD" PYTHONPATH="$APP" bash -lc \
  "cd $APP && set -a && source .env.production && set +a && .venv/bin/python scripts/reset_owner_login_password.py --email $EMAIL --password-env OWNER_LOGIN_PASSWORD"

systemctl restart worldcup-api
sleep 3

CODE=$(curl -sS -o /tmp/phase41c_login.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${OWNER_LOGIN_PASSWORD}\"}" \
  https://footballpredictor.it.com/api/auth/login)

python3 <<PY
import json
from pathlib import Path
data = json.loads(Path("/tmp/phase41c_login.json").read_text())
print("login_http_status=${CODE}")
print("login_has_jwt=", bool(data.get("access_token")))
print("login_role=", (data.get("user") or {}).get("role"))
PY

echo "password_stored_at=${PW_FILE}"
