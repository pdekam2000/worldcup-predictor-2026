#!/usr/bin/env bash
# Phase 38B — production deploy: Subscription System V1 (Phase 38A)
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase38b-${TS}"
TARBALL="${1:-/tmp/phase38b_deploy.tar.gz}"

echo "=== Phase 38B Production Deploy (Subscription V1) ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
echo "Pre-deploy commit: $(cat "${BACKUP}/pre_deploy_commit.txt")"

if [ -f data/football_intelligence.db ]; then
  cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db"
  echo "SQLite backed up"
fi

if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
  echo "Frontend dist backed up"
fi

if [ -f .env.production ]; then
  echo "$(readlink -f .env.production 2>/dev/null || realpath .env.production 2>/dev/null || echo "${APP}/.env.production")" > "${BACKUP}/env_production_path.txt"
fi

if [ -f /etc/systemd/system/worldcup-api.service ]; then
  cp -a /etc/systemd/system/worldcup-api.service "${BACKUP}/worldcup-api.service"
fi

set -a
# shellcheck disable=SC1091
source .env.production 2>/dev/null || true
set +a

if [ -n "${DATABASE_URL:-}" ] && command -v pg_dump >/dev/null 2>&1; then
  pg_dump "${DATABASE_URL}" -Fc -f "${BACKUP}/postgres.dump" 2>/dev/null && echo "PostgreSQL backed up" || echo "PostgreSQL backup skipped"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" worldcup_predictor/subscription alembic scripts/validate_phase38a_subscription_system.py 2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
  echo "Frontend deployed"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true
chown www-data:www-data "${APP}/data/football_intelligence.db" 2>/dev/null || true
chmod 664 "${APP}/data/football_intelligence.db" 2>/dev/null || true
mkdir -p "${APP}/data/logs"
chown -R www-data:www-data "${APP}/data/logs" 2>/dev/null || true

echo "=== 3. Env config (yes/no only) ==="
ENV_FILE="${APP}/.env.production"
touch "${ENV_FILE}"
chmod 640 "${ENV_FILE}" 2>/dev/null || true
chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true

_ensure_key() {
  local key="$1"
  local default_val="${2:-}"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    echo "${key}=configured"
  elif [ -n "${default_val}" ]; then
    echo "${key}=${default_val}" >> "${ENV_FILE}"
    echo "${key}=added_default"
  else
    echo "${key}=missing"
  fi
}

_ensure_key "ADMIN_CONTACT_EMAIL" "admin@worldcup-predictor.local"
_ensure_key "SMTP_HOST" ""
grep -q '^SMTP_PORT=' "${ENV_FILE}" 2>/dev/null || echo 'SMTP_PORT=587' >> "${ENV_FILE}"
echo "SMTP_PORT=configured"
grep -q '^SMTP_USE_TLS=' "${ENV_FILE}" 2>/dev/null || echo 'SMTP_USE_TLS=true' >> "${ENV_FILE}"
echo "SMTP_USE_TLS=configured"
if grep -q '^SMTP_USER=' "${ENV_FILE}" 2>/dev/null; then echo "SMTP_USER=configured"; else echo "SMTP_USER=optional_not_set"; fi
if grep -q '^SMTP_PASSWORD=' "${ENV_FILE}" 2>/dev/null; then echo "SMTP_PASSWORD=configured"; else echo "SMTP_PASSWORD=optional_not_set"; fi

echo "=== 4. Alembic migration ==="
set -a && source "${ENV_FILE}" && set +a
export APP_ENV=production
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/alembic upgrade head" \
  2>&1 | tee "${BACKUP}/alembic.log" | tail -10

echo "=== enum check ==="
set -a && source "${ENV_FILE}" && set +a
psql "${DATABASE_URL}" -t -c "SELECT unnest(enum_range(NULL::subscription_plan))::text;" 2>&1 | tee "${BACKUP}/enum_check.log"

echo "=== 5. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true

_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

echo "=== 6. Validations ==="
_run_validation scripts/validate_phase38a_subscription_system.py 2>&1 | tee "${BACKUP}/validate_phase38a.log" | tail -20
_run_validation scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a.log" | tail -12
_run_validation scripts/validate_phase36c_env_wiring.py 2>&1 | tee "${BACKUP}/validate_phase36c.log" | tail -10

echo "=== 7. Health ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo "=== 8. Subscription smoke (API logic) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -c \"
from worldcup_predictor.subscription.plan_limits import PLAN_MONTHLY_PREDICTION_LIMITS, normalize_plan
from worldcup_predictor.subscription.market_gating import market_allowed_for_plan
assert PLAN_MONTHLY_PREDICTION_LIMITS['free']==4
assert PLAN_MONTHLY_PREDICTION_LIMITS['starter']==28
assert PLAN_MONTHLY_PREDICTION_LIMITS['pro']==60
assert normalize_plan('elite')=='pro'
assert not market_allowed_for_plan('free','btts')
assert market_allowed_for_plan('starter','btts')
assert not market_allowed_for_plan('starter','goal_minute')
assert market_allowed_for_plan('pro','goal_minute')
print('subscription_smoke_ok')
\"" 2>&1 | tee "${BACKUP}/smoke_subscription.log"

echo -n "contact_admin_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/user/contact-admin -H "Content-Type: application/json" -d '{"subject":"x","message":"y"}' || echo "000"

echo -n "quota_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/user/quota || echo "000"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
