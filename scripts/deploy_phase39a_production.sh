#!/usr/bin/env bash
# Phase 39A — production deploy: SaaS Commercial Readiness
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase39a-${TS}"
TARBALL="${1:-/tmp/phase39a_deploy.tar.gz}"

echo "=== Phase 39A Production Deploy (Commercial Readiness) ==="
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

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/subscription \
  worldcup_predictor/api/routes/user.py \
  worldcup_predictor/api/routes/admin.py \
  scripts/validate_phase39a_commercial_readiness.py \
  2>/dev/null || true

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

if grep -q '^ADMIN_CONTACT_EMAIL=' "${ENV_FILE}" 2>/dev/null; then
  val=$(grep '^ADMIN_CONTACT_EMAIL=' "${ENV_FILE}" | cut -d= -f2-)
  if [ -n "${val}" ] && [ "${val}" != "admin@worldcup-predictor.local" ] && [ "${val}" != "placeholder@example.com" ]; then
    echo "ADMIN_CONTACT_EMAIL=configured"
  else
    echo "ADMIN_CONTACT_EMAIL=placeholder_update_recommended"
  fi
else
  echo "ADMIN_CONTACT_EMAIL=missing"
fi

if grep -q '^SMTP_HOST=' "${ENV_FILE}" 2>/dev/null; then echo "SMTP_HOST=configured"; else echo "SMTP_HOST=optional_not_set"; fi
if grep -q '^SMTP_USER=' "${ENV_FILE}" 2>/dev/null; then echo "SMTP_USER=configured"; else echo "SMTP_USER=optional_not_set"; fi
if grep -q '^SMTP_PASSWORD=' "${ENV_FILE}" 2>/dev/null; then echo "SMTP_PASSWORD=configured"; else echo "SMTP_PASSWORD=optional_not_set"; fi
grep -q '^SMTP_PORT=' "${ENV_FILE}" 2>/dev/null && echo "SMTP_PORT=configured" || echo "SMTP_PORT=default"
grep -q '^SMTP_USE_TLS=' "${ENV_FILE}" 2>/dev/null && echo "SMTP_USE_TLS=configured" || echo "SMTP_USE_TLS=default"

echo "=== 4. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true

_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

echo "=== 5. Validations ==="
_run_validation scripts/validate_phase39a_commercial_readiness.py 2>&1 | tee "${BACKUP}/validate_phase39a.log" | tail -25
_run_validation scripts/validate_phase38a_subscription_system.py 2>&1 | tee "${BACKUP}/validate_phase38a.log" | tail -15 || true
_run_validation scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a.log" | tail -12 || true

echo "=== 6. Health ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo "=== 7. Commercial smoke (API) ==="
echo -n "commercial_analytics_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/admin/commercial/analytics || echo "000"

echo -n "contact_admin_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/user/contact-admin \
  -H "Content-Type: application/json" \
  -d '{"subject":"x","message":"y","category":"support"}' || echo "000"

echo -n "quota_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/user/quota || echo "000"

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -c \"
from worldcup_predictor.subscription.commercial_analytics import build_commercial_analytics
from worldcup_predictor.subscription.commercial_readiness import run_commercial_readiness_audit
a = build_commercial_analytics()
r = run_commercial_readiness_audit()
assert 'total_users' in a
assert r['readiness_score'] >= 70
print('commercial_smoke_ok score=', r['readiness_score'])
\"" 2>&1 | tee "${BACKUP}/smoke_commercial.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
