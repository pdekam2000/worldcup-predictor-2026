#!/usr/bin/env bash
# Phase 5 localhost + HTTPS smoke tests (production). Never prints API key.
set -euo pipefail
ENV_FILE=/etc/worldcup-gpt-actions/environment
# shellcheck disable=SC1090
source "$ENV_FILE"
BASE_LOCAL="http://127.0.0.1:8770"
BASE_PUBLIC="https://footballpredictor.it.com"
TODAY=$(date +%F)
HDR=(-H "Authorization: Bearer ${GPT_ACTIONS_API_KEY}" -H "Accept: application/json")

echo "=== LOCALHOST MATRIX ==="
echo "| Action | Method | Path | Auth | Result |"
echo "| --- | --- | --- | --- | --- |"

code=$(curl -s -o /tmp/gpt_noauth.json -w '%{http_code}' "${BASE_LOCAL}/api/gpt-actions/v1/system/status")
echo "| getSystemStatus | GET | /system/status | none | HTTP ${code} |"

code=$(curl -s -o /tmp/gpt_bad.json -w '%{http_code}' -H "Authorization: Bearer bad-key" "${BASE_LOCAL}/api/gpt-actions/v1/system/status")
echo "| getSystemStatus | GET | /system/status | bad | HTTP ${code} |"

code=$(curl -s -o /tmp/gpt_status.json -w '%{http_code}' "${HDR[@]}" "${BASE_LOCAL}/api/gpt-actions/v1/system/status")
echo "| getSystemStatus | GET | /system/status | bearer | HTTP ${code} |"

code=$(curl -s -o /tmp/gpt_discover.json -w '%{http_code}' "${HDR[@]}" "${BASE_LOCAL}/api/gpt-actions/v1/matches/discover?date=${TODAY}&timezone=Europe/Vienna")
echo "| discoverTodayMatches | GET | /matches/discover | bearer | HTTP ${code} |"

code=$(curl -s -o /tmp/gpt_filter.json -w '%{http_code}' "${HDR[@]}" -H 'Content-Type: application/json' -d "{\"date\":\"${TODAY}\",\"timezone\":\"Europe/Vienna\",\"filter\":{\"home_odds_gt\":1.5}}" "${BASE_LOCAL}/api/gpt-actions/v1/matches/filter-odds")
echo "| filterMatchesByOdds | POST | /matches/filter-odds | bearer | HTTP ${code} |"

FID=$(python3 - <<'PY'
import json
try:
    d=json.load(open('/tmp/gpt_discover.json'))
    m=(d.get('matches') or [])
    print(m[0]['fixture_id'] if m else '')
except Exception:
    print('')
PY
)

if [[ -n "${FID}" ]]; then
  BODY="{\"date\":\"${TODAY}\",\"timezone\":\"Europe/Vienna\",\"fixture_ids\":[${FID}],\"include_all_predictions\":true,\"select_best\":1,\"refresh_if_stale\":false}"
else
  BODY="{\"date\":\"${TODAY}\",\"timezone\":\"Europe/Vienna\",\"fixture_ids\":[999999999],\"include_all_predictions\":true,\"select_best\":1,\"refresh_if_stale\":false}"
fi

start=$(date +%s%N)
code=$(curl -s -o /tmp/gpt_job_create.json -w '%{http_code}' "${HDR[@]}" -H 'Content-Type: application/json' -H 'Idempotency-Key: phase5-smoke-1' -d "${BODY}" "${BASE_LOCAL}/api/gpt-actions/v1/prediction-jobs")
end=$(date +%s%N)
elapsed_ms=$(( (end - start) / 1000000 ))
echo "| startPredictionJob | POST | /prediction-jobs | bearer | HTTP ${code} (${elapsed_ms}ms) |"

JOB=$(python3 - <<'PY'
import json
print(json.load(open('/tmp/gpt_job_create.json')).get('job_id',''))
PY
)
echo "JOB_ID=${JOB}"

status="queued"
for i in $(seq 1 25); do
  code=$(curl -s -o /tmp/gpt_job_poll.json -w '%{http_code}' "${HDR[@]}" "${BASE_LOCAL}/api/gpt-actions/v1/prediction-jobs/${JOB}")
  status=$(python3 - <<'PY'
import json
print(json.load(open('/tmp/gpt_job_poll.json')).get('status',''))
PY
)
  echo "poll_${i}=HTTP_${code}_status_${status}"
  if [[ "${status}" == "completed" || "${status}" == "partial" || "${status}" == "failed" ]]; then
    break
  fi
  sleep 1
done
echo "| getPredictionJob | GET | /prediction-jobs/{id} | bearer | final ${status} |"

python3 - <<'PY'
import json
p=json.load(open('/tmp/gpt_job_poll.json'))
r=p.get('result') or {}
preds=r.get('predictions') or []
print('prediction_count', len(preds))
if preds:
    x=preds[0]
    print('fixture_id', x.get('fixture_id'))
    print('wde_keys', sorted((x.get('wde') or {}).keys()))
    print('ecse_top1', (x.get('ecse') or {}).get('top1'))
PY

echo "=== PUBLIC HTTPS SPOT CHECK ==="
code=$(curl -s -o /tmp/gpt_pub_noauth.json -w '%{http_code}' "${BASE_PUBLIC}/api/gpt-actions/v1/system/status")
echo "public_no_auth=${code}"
code=$(curl -s -o /tmp/gpt_pub_ok.json -w '%{http_code}' "${HDR[@]}" "${BASE_PUBLIC}/api/gpt-actions/v1/system/status")
echo "public_valid_auth=${code}"
code=$(curl -s -o /tmp/gpt_api_health.json -w '%{http_code}' "${BASE_PUBLIC}/api/health")
echo "saas_api_health=${code}"
