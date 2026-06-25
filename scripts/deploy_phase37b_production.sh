#!/usr/bin/env bash
# Phase 37B — production deploy: 36C + 36B + 37A
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase37b-${TS}"
TARBALL="${1:-/tmp/phase37b_deploy.tar.gz}"

echo "=== Phase 37B Production Deploy (36C + 36B + 37A) ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

# --- 1. Backup ---
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
  # Never copy or print contents
fi

if [ -f /etc/systemd/system/worldcup-api.service ]; then
  cp -a /etc/systemd/system/worldcup-api.service "${BACKUP}/worldcup-api.service"
fi

set -a
# shellcheck disable=SC1091
source .env.production 2>/dev/null || true
set +a

if [ -n "${DATABASE_URL:-}" ]; then
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump "${DATABASE_URL}" -Fc -f "${BACKUP}/postgres.dump" 2>/dev/null && echo "PostgreSQL backed up" || echo "PostgreSQL backup skipped (pg_dump failed)"
  fi
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor \
  scripts \
  alembic \
  deployment/systemd \
  2>/dev/null || true
echo "Repo snapshot: ${BACKUP}/repo_snapshot_pre.tar.gz"

# --- 2. Extract overlay ---
echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
  echo "Frontend deployed"
fi

# systemd units (preserve APP_ENV=production)
if [ -d "${APP}/deployment/systemd" ]; then
  cp "${APP}/deployment/systemd/worldcup-api.service" /etc/systemd/system/ 2>/dev/null || true
  cp "${APP}/deployment/systemd/worldcup-daily-predict.service" /etc/systemd/system/ 2>/dev/null || true
  systemctl daemon-reload 2>/dev/null || true
fi

# permissions
chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true
chown www-data:www-data "${APP}/data" 2>/dev/null || true
chown www-data:www-data "${APP}/data/football_intelligence.db" 2>/dev/null || true
chmod 664 "${APP}/data/football_intelligence.db" 2>/dev/null || true
mkdir -p "${APP}/data/logs" "${APP}/.cache"
chown -R www-data:www-data "${APP}/data/logs" "${APP}/.cache" 2>/dev/null || true
chmod -R u+rwX "${APP}/.cache" 2>/dev/null || true

# --- 3. Admin keys (ensure present, never print) ---
echo "=== 3. Admin keys check ==="
ENV_FILE="${APP}/.env.production"
touch "${ENV_FILE}"
chmod 640 "${ENV_FILE}" 2>/dev/null || true
chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true

_ensure_env_key() {
  local key="$1"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    echo "${key}=configured"
  else
    local val
    val=$(openssl rand -hex 24)
    echo "${key}=${val}" >> "${ENV_FILE}"
    echo "${key}=generated"
  fi
}

grep -q '^APP_ENV=production' "${ENV_FILE}" 2>/dev/null || echo 'APP_ENV=production' >> "${ENV_FILE}"
echo "APP_ENV=production (configured)"
_ensure_env_key "ADMIN_ACCESS_KEY"
_ensure_env_key "SUPER_ADMIN_ACCESS_KEY"

# --- 4. Alembic migration ---
echo "=== 4. Alembic migration ==="
set -a && source "${ENV_FILE}" && set +a
export APP_ENV=production
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/alembic upgrade head" \
  2>&1 | tee "${BACKUP}/alembic.log" | tail -15

# verify super_admin enum
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -c \"
from sqlalchemy import create_engine, text
import os
e = create_engine(os.environ['DATABASE_URL'])
with e.connect() as c:
    r = c.execute(text(\\\"SELECT unnest(enum_range(NULL::user_role))::text\\\")).fetchall()
    print('user_role_enum:', [x[0] for x in r])
\"" 2>&1 | tee "${BACKUP}/enum_check.log"

# --- 5. Restart services ---
echo "=== 5. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true

# --- helper ---
_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

# --- 6. Env diagnostic ---
echo "=== 6. Env diagnostic ==="
_run_validation scripts/diagnose_env_providers.py 2>&1 | tee "${BACKUP}/diagnose_env.log"

# --- 7. Validations ---
echo "=== 7. Validations ==="
_run_validation scripts/validate_phase36c_env_wiring.py 2>&1 | tee "${BACKUP}/validate_phase36c.log" | tail -12
_run_validation scripts/validate_phase36b_placeholder_repair.py 2>&1 | tee "${BACKUP}/validate_phase36b.log" | tail -12
_run_validation scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a.log" | tail -15
_run_validation scripts/validate_phase34b_stale_confidence_cache_fix.py 2>&1 | tee "${BACKUP}/validate_phase34b.log" | tail -10
_run_validation scripts/validate_phase35_accuracy_driven_optimization.py 2>&1 | tee "${BACKUP}/validate_phase35.log" | tail -10

# --- 8. Fixture 1489393 before repair ---
echo "=== 8. Fixture 1489393 before repair ==="
curl -sf "http://127.0.0.1:8000/api/predict/1489393" 2>/dev/null | tee "${BACKUP}/fixture1489393_before.json" | head -c 400 || echo "(predict unavailable)"
echo ""

# --- 9. Repair placeholder ---
echo "=== 9. Repair placeholder 1489393 ==="
_run_validation "scripts/repair_placeholder_predictions.py --fixture-id 1489393" 2>&1 | tee "${BACKUP}/repair_1489393.log" | tail -20

# --- 10. After repair + cache reuse ---
echo "=== 10. Fixture 1489393 after repair ==="
curl -sf -X POST "http://127.0.0.1:8000/api/predict/1489393?force_refresh=true" 2>/dev/null | tee "${BACKUP}/fixture1489393_after_refresh.json" | head -c 500 || true
echo ""
curl -sf "http://127.0.0.1:8000/api/predict/1489393" 2>/dev/null | tee "${BACKUP}/fixture1489393_cached.json" | head -c 500 || true
echo ""

# --- 11. Smoke tests ---
echo "=== 11. Smoke tests ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo -n "admin_health_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/admin/health || echo "000"

echo -n "admin_gate_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/admin/gate/verify -H "Content-Type: application/json" -d '{"access_key":"x"}' || echo "000"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
