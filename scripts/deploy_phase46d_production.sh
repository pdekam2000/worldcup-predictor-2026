#!/usr/bin/env bash
# Phase 46D — production deploy: provider utilization
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase46d-${TS}"
TARBALL="${1:-/tmp/phase46d_deploy.tar.gz}"

echo "=== Phase 46D Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
chmod +x scripts/deploy_phase46d_production.sh scripts/phase46d_production_smoke.py 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase46d_production.sh scripts/validate_phase46d_provider_utilization.py scripts/phase46d_production_smoke.py 2>/dev/null || true

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 4. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase46d_provider_utilization.py" \
  2>&1 | tee "${BACKUP}/validate_46d.log" | tail -30

echo "=== 6. Production smoke ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/phase46d_production_smoke.py" \
  2>&1 | tee "${BACKUP}/smoke_46d.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
