#!/usr/bin/env bash
# Phase 64 — production autonomous once (owner API, fixture limit 10).
set -euo pipefail
EMAIL="${EMAIL:-kamangar.pedram@gmail.com}"
PW_FILE="${PW_FILE:-/root/.wcp_owner_requested_password.txt}"
BASE="${BASE:-https://footballpredictor.it.com}"

OWNER_LOGIN_PASSWORD="$(tr -d '\r\n' < "$PW_FILE")"

curl -sS -H "Content-Type: application/json" \
  --data-binary "{\"email\":\"${EMAIL}\",\"password\":\"${OWNER_LOGIN_PASSWORD}\"}" \
  -o /tmp/phase64_login.json \
  "${BASE}/api/auth/login"

TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/phase64_login.json')).get('access_token',''))")
if [ -z "$TOKEN" ]; then
  echo "LOGIN_FAILED"
  head -c 300 /tmp/phase64_login.json
  exit 1
fi

curl -sS -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -X POST -d '{"dry_run":false,"fixture_limit":10}' \
  -o /tmp/phase64_autonomous_run.json \
  "${BASE}/api/owner/autonomous/run-once"

python3 <<'PY'
import json
p = json.load(open("/tmp/phase64_autonomous_run.json"))
r = p.get("report") or {}
d = r.get("discovery") or {}
pred = r.get("predictions") or {}
ev = r.get("evaluation") or {}
print("status=" + str(r.get("status")))
print("fixtures_discovered=" + str(d.get("fixture_count", d.get("fixtures_discovered"))))
print("production_snapshots=" + str(pred.get("production_snapshots")))
print("elite_snapshots=" + str(pred.get("elite_snapshots")))
print("pending_evaluations=" + str(ev.get("pending")))
print("api_calls=" + str(r.get("api_calls_used")))
print("errors=" + str(pred.get("errors")))
PY
