#!/usr/bin/env bash
# Hotfix Pack 2 — production deploy
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/hotfix-pack2-${TS}"
TARBALL="${1:-/tmp/hotfix_pack2_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

mkdir -p "${BACKUP}"
cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
if [ -d "${FRONTEND_DIST}" ]; then
  tar czf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" "$(basename "${FRONTEND_DIST}")"
fi

tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r$//' scripts/_remote_deploy_hotfix_pack2.sh scripts/validate_hotfix_pack2_evaluation_goal_timing.py scripts/hotfix_pack2_re_evaluate_finished.py 2>/dev/null || true

cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

systemctl restart worldcup-api
sleep 6
systemctl is-active --quiet worldcup-api
nginx -t
systemctl reload nginx

cd "${APP}"
.venv/bin/python scripts/hotfix_pack2_re_evaluate_finished.py 200 | tee "${BACKUP}/re_evaluate.log"
.venv/bin/python scripts/validate_hotfix_pack2_evaluation_goal_timing.py | tee "${BACKUP}/validate.log"

echo "DEPLOY_OK backup=${BACKUP}"
