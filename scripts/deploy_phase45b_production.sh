#!/usr/bin/env bash
# Phase 45B — production deploy: data trust, result refresh, UI fixes
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase45b-${TS}"
TARBALL="${1:-/tmp/phase45b_deploy.tar.gz}"

echo "=== Phase 45B Production Deploy ==="
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

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
chmod +x scripts/deploy_phase45b_smoke.sh scripts/phase45b_post_deploy.py 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase45b_production.sh scripts/deploy_phase45b_smoke.sh scripts/phase45b_post_deploy.py 2>/dev/null || true

if [ -d base44-d/dist ]; then
  mkdir -p "${FRONTEND}"
  rm -rf "${FRONTEND:?}/"*
  cp -a base44-d/dist/. "${FRONTEND}/"
  echo "Frontend dist deployed"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true
chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true

echo "=== 3. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || true

echo "=== 4. Post-deploy quarantine + summary rebuild ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/phase45b_post_deploy.py" \
  2>&1 | tee "${BACKUP}/post_deploy.log"

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase45b_data_trust_live_results_ui.py" \
  2>&1 | tee "${BACKUP}/validate_45b.log" | tail -30

echo "=== 6. Smoke ==="
bash scripts/deploy_phase45b_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
