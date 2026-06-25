#!/bin/bash
# Phase 54H-3 — up to 5 live pressure probes on server (no secrets printed).
set -eu
ENV=/opt/worldcup-predictor/.env.production
TOKEN=$(grep -m1 '^SPORTMONKS_API_TOKEN=' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
echo PROBE_TOKEN_LENGTH=${#TOKEN}
FIXTURES="1058477:champions_league 1059951:europa_league 18151405:conference_league 19609127:world_cup 99999999:control_invalid"
N=0
for item in $FIXTURES; do
  [ "$N" -ge 5 ] && break
  FID=${item%%:*}
  LABEL=${item##*:}
  HTTP=$(curl -sS -o "/tmp/p54h3_${FID}.json" -w "%{http_code}" \
    "https://api.sportmonks.com/v3/football/fixtures/${FID}?api_token=${TOKEN}&include=participants%3Bpressure")
  ROWS=$(python3 -c "import json;d=json.load(open('/tmp/p54h3_${FID}.json'));print(len((d.get('data') or {}).get('pressure') or []))" 2>/dev/null || echo 0)
  echo "PROBE label=${LABEL} fixture_id=${FID} http=${HTTP} pressure_rows=${ROWS}"
  rm -f "/tmp/p54h3_${FID}.json"
  N=$((N+1))
done
