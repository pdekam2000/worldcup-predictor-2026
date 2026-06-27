#!/usr/bin/env bash
# HOTFIX — market-level result evaluation + best bet winrate
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-market-level-${TS}"
TARBALL="${1:-/tmp/hotfix_market_level_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist
NGINX_CONF=/etc/nginx/sites-enabled/worldcup

echo "=== HOTFIX Market-Level Evaluation Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Pre-deploy backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
systemctl is-active worldcup-api > "${BACKUP}/service_status_pre.txt" 2>/dev/null || true
systemctl is-active nginx >> "${BACKUP}/service_status_pre.txt" 2>/dev/null || true
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
if [ -d "${FRONTEND_DIST}" ]; then
  tar czf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" "$(basename "${FRONTEND_DIST}")"
fi
if [ -f "${NGINX_CONF}" ]; then
  cp -a "${NGINX_CONF}" "${BACKUP}/nginx_worldcup.conf" 2>/dev/null || true
fi
if command -v pg_dump >/dev/null 2>&1 && [ -f .env.production ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.production
  set +a
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres_pre.sql" 2>/dev/null || true
  fi
fi
tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/market_level_evaluation.py \
  worldcup_predictor/automation/worldcup_background/pick_evaluator.py \
  worldcup_predictor/api/archive_evaluation_join.py \
  worldcup_predictor/api/evaluated_results.py \
  worldcup_predictor/api/global_prediction_archive.py \
  worldcup_predictor/api/routes/results.py \
  base44-d/src/lib/archiveFilters.js \
  base44-d/src/lib/archiveStatus.js \
  base44-d/src/components/archive/MarketBreakdownPanel.jsx \
  base44-d/src/components/archive/ArchiveCard.jsx \
  base44-d/src/pages/PredictionResultsPage.jsx \
  base44-d/src/pages/ArchivePage.jsx \
  base44-d/src/api/saasApi.js \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r$//' \
  scripts/deploy_hotfix_market_level_production.sh \
  scripts/deploy_hotfix_market_level_smoke.sh \
  scripts/refresh_market_level_evaluations.py \
  scripts/validate_hotfix_market_level_result_evaluation.py \
  2>/dev/null || true
chmod +x scripts/deploy_hotfix_market_level_smoke.sh 2>/dev/null || true
chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== 4. Restart API ==="
systemctl restart worldcup-api
sleep 6
if ! systemctl is-active --quiet worldcup-api; then
  echo "API_FAILED — rolling back snapshot"
  tar xzf "${BACKUP}/repo_snapshot_pre.tar.gz" -C "${APP}" 2>/dev/null || true
  if [ -f "${BACKUP}/frontend_dist_pre.tar.gz" ]; then
    tar xzf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" 2>/dev/null || true
  fi
  systemctl restart worldcup-api || true
  echo "ROLLED_BACK_API"
  exit 1
fi
systemctl status worldcup-api --no-pager | head -15 | tee "${BACKUP}/api_status_post.txt"

echo "=== 5. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 6. Refresh market-level evaluations (dry-run) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/refresh_market_level_evaluations.py --dry-run" \
  2>&1 | tee "${BACKUP}/refresh_dry_run.log"

echo "=== 7. Refresh market-level evaluations (apply) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/refresh_market_level_evaluations.py" \
  2>&1 | tee "${BACKUP}/refresh_apply.log"

echo "=== 8. Smoke tests ==="
cd "${APP}"
bash scripts/deploy_hotfix_market_level_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "=== 9. Post-deploy validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/validate_hotfix_market_level_result_evaluation.py" \
  2>&1 | tee "${BACKUP}/validate.log" | tail -25

git rev-parse HEAD > "${BACKUP}/post_deploy_commit.txt" 2>/dev/null || true
echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
