#!/usr/bin/env bash
# HOTFIX — Premium plan 404 — production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-premium-plan-404-${TS}"
TARBALL="${1:-/tmp/hotfix_premium_plan_404_deploy.tar.gz}"

echo "=== HOTFIX Premium Plan 404 Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
echo "Pre-deploy commit: $(cat "${BACKUP}/pre_deploy_commit.txt")"

if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
  echo "Frontend dist backed up"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/billing.py \
  worldcup_predictor/billing/billing_service.py \
  worldcup_predictor/billing/schemas.py \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  rm -rf "${FRONTEND:?}/"*
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
  echo "Frontend deployed"
fi

if [ -f "${APP}/scripts/validate_hotfix_premium_plan_404.py" ]; then
  echo "Validation script deployed"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
systemctl is-active nginx

echo "=== 4. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   .venv/bin/python scripts/validate_hotfix_premium_plan_404.py" \
  2>&1 | tee "${BACKUP}/validate_hotfix.log" | tail -35

echo "=== 5. Smoke ==="
bash scripts/deploy_hotfix_premium_plan_404_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
