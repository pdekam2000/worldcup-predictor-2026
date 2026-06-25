#!/usr/bin/env bash
# Phase 54H-3 — server Sportmonks pressure token probe (no secrets printed).
set -eu
ENV="/opt/worldcup-predictor/.env.production"
if [ ! -f "$ENV" ]; then
  echo "SERVER_ENV_MISSING=1"
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$ENV"
set +a
if [ -z "${SPORTMONKS_API_TOKEN:-}" ]; then
  echo "SERVER_TOKEN_PRESENT=0"
  exit 1
fi
echo "SERVER_TOKEN_PRESENT=1"
echo "SERVER_TOKEN_LENGTH=${#SPORTMONKS_API_TOKEN}"
FID="${1:-19135063}"
INCLUDE="participants%3Bpressure"
URL="https://api.sportmonks.com/v3/football/fixtures/${FID}?api_token=${SPORTMONKS_API_TOKEN}&include=${INCLUDE}"
HTTP=$(curl -sS -o /tmp/phase54h3_pressure.json -w "%{http_code}" "$URL")
echo "SERVER_HTTP_STATUS=${HTTP}"
python3 <<'PY'
import json
from pathlib import Path
p = Path("/tmp/phase54h3_pressure.json")
try:
    d = json.loads(p.read_text())
except Exception as exc:
    print("SERVER_PARSE_ERROR", exc)
    raise SystemExit(0)
data = d.get("data") or {}
pres = data.get("pressure") or []
if not isinstance(pres, list):
    pres = []
mins = sorted({int(x.get("minute") or 0) for x in pres if isinstance(x, dict)})
parts = sorted({int(x.get("participant_id") or 0) for x in pres if isinstance(x, dict) if x.get("participant_id")})
print("SERVER_PRESSURE_ROWS", len(pres))
print("SERVER_PARTICIPANTS", parts[:8])
print("SERVER_UNIQUE_MINUTES", len(mins))
if mins:
    print("SERVER_MINUTE_MIN", mins[0])
    print("SERVER_MINUTE_MAX", mins[-1])
msg = d.get("message")
if msg:
    print("SERVER_MESSAGE", str(msg)[:120])
PY
rm -f /tmp/phase54h3_pressure.json
