#!/usr/bin/env bash
# Phase 51G — production deploy: EGIE monitoring dashboard polish
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase51g-${TS}"
TARBALL="${1:-/tmp/phase51g_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase 51G Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
if [ -d "${FRONTEND_DIST}" ]; then
  cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
fi
if [ -f data/egie/scheduler_state.json ]; then
  cp -a data/egie/scheduler_state.json "${BACKUP}/scheduler_state.json" 2>/dev/null || true
fi

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
chmod +x scripts/deploy_phase51g_production.sh scripts/deploy_phase51g_smoke.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase51g_production.sh scripts/deploy_phase51g_smoke.sh scripts/validate_phase51g_egie_dashboard_polish.py 2>/dev/null || true
chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Run EGIE evaluation loop (real data refresh) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python main.py egie-goal-timing-evaluation --limit 200 --max-api-calls 20" \
  2>&1 | tee "${BACKUP}/eval_run.log" | tail -15

echo "=== 4. Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== 5. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 6. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 7. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase51g_egie_dashboard_polish.py" \
  2>&1 | tee "${BACKUP}/validate_51g.log" | tail -40

echo "=== 8. Smoke ==="
bash scripts/deploy_phase51g_smoke.sh 2>&1 | tee "${BACKUP}/smoke_51g.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
