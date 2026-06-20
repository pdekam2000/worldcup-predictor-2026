#!/usr/bin/env bash
# Read-only production Sportmonks env audit — never prints secret values.
set -euo pipefail
APP="${APP_ROOT:-/opt/worldcup-predictor}"
ENV_FILE="$APP/.env.production"

echo "=== ENV FILE ==="
if [ -f "$ENV_FILE" ]; then echo "env_file_exists: true"; else echo "env_file_exists: false"; fi

check_var() {
  local name="$1"
  if [ ! -f "$ENV_FILE" ]; then
    echo "${name}_in_file: false"
    echo "${name}_non_empty: false"
    return
  fi
  if grep -qE "^${name}=" "$ENV_FILE" 2>/dev/null; then
    echo "${name}_in_file: true"
    val=$(grep -E "^${name}=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//')
    if [ -n "$val" ]; then echo "${name}_non_empty: true"; else echo "${name}_non_empty: false"; fi
  else
    echo "${name}_in_file: false"
    echo "${name}_non_empty: false"
  fi
}

check_var SPORTMONKS_API_TOKEN
check_var SPORTMONKS_API_KEY
check_var SPORTMONKS_BASE_URL

echo "=== SYSTEMD ==="
if systemctl is-active worldcup-api >/dev/null 2>&1; then echo "worldcup-api: active"; else echo "worldcup-api: inactive"; fi

echo "=== RUNTIME SETTINGS ==="
cd "$APP"
if [ ! -d .venv ]; then
  echo "venv_missing: true"
  exit 0
fi

.venv/bin/python - <<'PY'
from worldcup_predictor.config.settings import Settings

s = Settings(_env_file="/opt/worldcup-predictor/.env.production")
token_src = "none"
if s.sportmonks_api_token.strip():
    token_src = "SPORTMONKS_API_TOKEN"
elif s.sportmonks_api_key.strip():
    token_src = "SPORTMONKS_API_KEY"
print(f"runtime_sportmonks_configured: {s.sportmonks_configured}")
print(f"runtime_token_source: {token_src}")
print(f"runtime_token_length: {len(s.sportmonks_effective_token)}")
print(f"runtime_base_url: {s.sportmonks_base_url}")
PY

.venv/bin/python - <<'PY'
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.config.settings import Settings

s = Settings(_env_file="/opt/worldcup-predictor/.env.production")
result = SportmonksProvider(s).run_world_cup_connectivity_test()
print(f"connectivity_configured: {result.configured}")
print(f"connectivity_connected: {result.connected}")
print(f"connectivity_status_code: {result.status_code}")
print(f"connectivity_endpoint: {result.endpoint_path}")
print(f"connectivity_message: {result.message[:120]}")
PY
