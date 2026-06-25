#!/usr/bin/env bash
set -euo pipefail
EMAIL="${1:-kamangar.pedram@gmail.com}"
PW_FILE="${PW_FILE:-/root/.wcp_phase41c_owner_login.txt}"
OWNER_LOGIN_PASSWORD="$(tr -d '\r\n' < "$PW_FILE")"

CODE=$(curl -sS -o /tmp/em_login.json -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  --data-binary @- "https://footballpredictor.it.com/api/auth/login" <<EOF
{"email":"${EMAIL}","password":"${OWNER_LOGIN_PASSWORD}"}
EOF
)
echo "login_http=${CODE}"
python3 - <<'PY'
import json
p=json.load(open("/tmp/em_login.json"))
u=p.get("user") or {}
print("role=" + str(u.get("role")))
print("token=" + ("yes" if p.get("access_token") else "no"))
PY

TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/em_login.json')).get('access_token',''))")
if [ -n "$TOKEN" ]; then
  OC=$(curl -sS -o /tmp/em_owner.json -w '%{http_code}' \
    -H "Authorization: Bearer ${TOKEN}" \
    "https://footballpredictor.it.com/api/owner/overview")
  echo "owner_overview_http=${OC}"
fi

AUTH_CFG=$(curl -sS -o /tmp/em_cfg.json -w '%{http_code}' "https://footballpredictor.it.com/api/auth/config")
echo "auth_config_http=${AUTH_CFG}"
