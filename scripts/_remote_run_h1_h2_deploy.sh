#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-h1-h2-${TS}"
TARBALL="/tmp/hotfix_h1_h2_deploy.tar.gz"
FRONTEND_DIST=/var/www/worldcup/frontend/dist
LOG="${BACKUP}.log"
mkdir -p "${BACKUP}"
exec > >(tee "${LOG}") 2>&1
echo "=== HOTFIX H1+H2 Deploy ${TS} ==="
cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
if [ -d "${FRONTEND_DIST}" ]; then
  tar czf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" "$(basename "${FRONTEND_DIST}")"
fi
cp -a worldcup_predictor/api/routes/predictions.py "${BACKUP}/predictions.py" 2>/dev/null || true
tar xzf "${TARBALL}" -C "${APP}"
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true
systemctl restart worldcup-api
sleep 8
systemctl is-active worldcup-api
nginx -t
systemctl reload nginx
SKIP_FRONTEND_BUILD=1 HOTFIX_BASE_URL=https://footballpredictor.it.com "${APP}/.venv/bin/python" "${APP}/scripts/validate_hotfix_h1_match_detail_logo_flags.py" | tee "${BACKUP}/validate_h1.log"
HOTFIX_BASE_URL=https://footballpredictor.it.com bash "${APP}/scripts/deploy_hotfix_h1_h2_smoke.sh" | tee "${BACKUP}/smoke.log"
echo "DEPLOY_OK backup=${BACKUP} log=${LOG}"
