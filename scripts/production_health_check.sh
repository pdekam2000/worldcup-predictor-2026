#!/usr/bin/env bash
# Phase 2 — application and provider health checks (diagnostic policy).
set -Eeuo pipefail

APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
PROVIDERS_URL="${PROVIDERS_URL:-http://127.0.0.1:8000/api/health/providers}"
TIMEOUT="${HEALTH_TIMEOUT_SEC:-15}"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

fail_app() {
  log "APPLICATION_UNHEALTHY: $*"
  exit 1
}

warn_provider() {
  log "PROVIDER_DIAGNOSTIC_WARN: $*"
}

http_get() {
  local url="$1"
  curl -sf --max-time "${TIMEOUT}" "${url}"
}

log "health_check app=${HEALTH_URL}"

APP_BODY="$(http_get "${HEALTH_URL}" 2>/dev/null || fail_app "GET ${HEALTH_URL} failed")"
if ! echo "${APP_BODY}" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
  fail_app "application health status not ok: ${APP_BODY}"
fi
log "APPLICATION_HEALTH_OK"

PROVIDER_BODY="$(http_get "${PROVIDERS_URL}" 2>/dev/null || warn_provider "GET ${PROVIDERS_URL} failed (non-fatal for code deploy)")"
if [[ -n "${PROVIDER_BODY}" ]]; then
  echo "${PROVIDER_BODY}" | python3 - <<'PY'
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(0)
try:
    d = json.loads(raw)
except json.JSONDecodeError:
    print("PROVIDER_DIAGNOSTIC: invalid JSON", file=sys.stderr)
    sys.exit(0)

# Application-level provider endpoint returns status ok even when keys missing.
# Distinguish credential gaps vs external outage for operators only.
missing = []
for key in ("api_football_configured", "sportmonks_configured", "the_odds_api_configured"):
    if d.get(key) is False:
        missing.append(key)
if missing:
    print("PROVIDER_CREDENTIAL_MISSING: " + ", ".join(missing))
else:
    print("PROVIDER_DIAGNOSTIC_OK")
PY
fi

log "HEALTH_CHECK_COMPLETE"
exit 0
