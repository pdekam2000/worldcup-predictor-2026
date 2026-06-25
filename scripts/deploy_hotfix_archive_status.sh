#!/usr/bin/env bash
# Hotfix — archive evaluation status join
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-archive-status-${TS}"
TARBALL="${1:-/tmp/hotfix_archive_status_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Hotfix Archive Status Deploy ==="
mkdir -p "${BACKUP}"
cd "${APP}"

git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
[ -d "${FRONTEND_DIST}" ] && cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true

tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r$//' scripts/deploy_hotfix_archive_status.sh scripts/validate_hotfix_archive_status_evaluation_join.py 2>/dev/null || true
chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
nginx -t && systemctl reload nginx

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_hotfix_archive_status_evaluation_join.py" \
  | tee "${BACKUP}/validate.log" | tail -30

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
