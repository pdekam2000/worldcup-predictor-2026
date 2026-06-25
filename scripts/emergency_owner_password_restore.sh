#!/usr/bin/env bash
# Restore owner password to project-owner requested value — no plaintext in logs.
set -euo pipefail
APP=/opt/worldcup-predictor
EMAIL="${EMAIL:-kamangar.pedram@gmail.com}"
PW_SOURCE="${PW_SOURCE:-/root/.wcp_owner_requested_password.txt}"

if [[ ! -f "$PW_SOURCE" ]]; then
  echo "Missing password source file: $PW_SOURCE" >&2
  exit 1
fi

export OWNER_LOGIN_PASSWORD
OWNER_LOGIN_PASSWORD="$(tr -d '\r\n' < "$PW_SOURCE")"
if [[ ${#OWNER_LOGIN_PASSWORD} -lt 8 ]]; then
  echo "Password source too short" >&2
  exit 1
fi

cd "$APP"
set -a && source .env.production && set +a

echo "=== Ensure owner account ==="
sudo -u www-data env OWNER_LOGIN_PASSWORD="$OWNER_LOGIN_PASSWORD" PYTHONPATH="$APP" bash -lc \
  "cd $APP && set -a && source .env.production && set +a && .venv/bin/python scripts/ensure_owner_account.py --email $EMAIL"

echo "=== Reset owner password (bcrypt hash only) ==="
sudo -u www-data env OWNER_LOGIN_PASSWORD="$OWNER_LOGIN_PASSWORD" PYTHONPATH="$APP" bash -lc \
  "cd $APP && set -a && source .env.production && set +a && .venv/bin/python scripts/reset_owner_login_password.py --email $EMAIL --password-env OWNER_LOGIN_PASSWORD"

systemctl restart worldcup-api
sleep 3

echo "=== Login smoke ==="
bash "$APP/scripts/emergency_login_smoke.sh" "$EMAIL"
