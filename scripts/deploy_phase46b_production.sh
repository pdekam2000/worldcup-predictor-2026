#!/usr/bin/env bash
# Phase 46B — production deploy: historical prediction recovery
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase46b-${TS}"
TARBALL="${1:-/tmp/phase46b_deploy.tar.gz}"

echo "=== Phase 46B Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
fi
if [ -d .cache/predictions ]; then
  mkdir -p "${BACKUP}/prediction_cache"
  cp -a .cache/predictions/. "${BACKUP}/prediction_cache/" 2>/dev/null || true
fi

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
chmod +x scripts/deploy_phase46b_production.sh scripts/phase46b_post_deploy.py 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase46b_production.sh scripts/phase46b_post_deploy.py scripts/validate_phase46b_historical_recovery.py 2>/dev/null || true

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || true

echo "=== 4. Post-deploy legacy import ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/phase46b_post_deploy.py" \
  2>&1 | tee "${BACKUP}/post_deploy.log"

echo "=== 5. Production smoke ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/phase46b_production_smoke.py" \
  2>&1 | tee "${BACKUP}/smoke_46b.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
