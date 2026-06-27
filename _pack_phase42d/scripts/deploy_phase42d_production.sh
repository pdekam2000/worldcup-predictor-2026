#!/usr/bin/env bash
# Phase 42D — production deploy: Global Archive + Best Tips Performance Center
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase42d-${TS}"
TARBALL="${1:-/tmp/phase42d_deploy.tar.gz}"

echo "=== Phase 42D Production Deploy (Global Archive + Best Tips) ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
chown www-data:www-data "${BACKUP}" 2>/dev/null || chmod 775 "${BACKUP}"

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
  cp -a .env.production "${BACKUP}/env.production"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/global_prediction_archive.py \
  worldcup_predictor/api/performance_center.py \
  worldcup_predictor/api/routes/performance.py \
  worldcup_predictor/api/routes/history.py \
  worldcup_predictor/api/prediction_archive_detail.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/database/repository.py \
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
else
  echo "=== 2b. Build frontend on server ==="
  cd "${APP}/base44-d"
  npm ci
  npm run build
  mkdir -p "${FRONTEND}"
  rm -rf "${FRONTEND:?}/"*
  cp -a dist/. "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  cd "${APP}"
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
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase42d_global_archive_best_tips.py" \
  2>&1 | tee "${BACKUP}/validate_42d.log" | tail -30

echo "=== 5. Smoke ==="
bash scripts/deploy_phase42d_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
