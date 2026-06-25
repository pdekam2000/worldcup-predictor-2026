#!/bin/bash
set -eu
ENV=/opt/worldcup-predictor/.env.production
grep -q '^SPORTMONKS_API_TOKEN=' "$ENV"
TOKEN=$(grep -m1 '^SPORTMONKS_API_TOKEN=' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
echo SERVER_TOKEN_PRESENT=1
echo SERVER_TOKEN_LENGTH=${#TOKEN}
FID=19135063
HTTP=$(curl -sS -o /tmp/p54h3.json -w "%{http_code}" "https://api.sportmonks.com/v3/football/fixtures/${FID}?api_token=${TOKEN}&include=participants%3Bpressure")
echo SERVER_HTTP_STATUS=${HTTP}
python3 -c "import json;d=json.load(open('/tmp/p54h3.json'));p=(d.get('data') or {}).get('pressure') or [];print('SERVER_PRESSURE_ROWS',len(p));m=d.get('message');print('SERVER_MESSAGE',str(m)[:80] if m else '')"
rm -f /tmp/p54h3.json
