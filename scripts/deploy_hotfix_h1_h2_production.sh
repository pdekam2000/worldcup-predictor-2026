#!/usr/bin/env bash
# HOTFIX H1+H2 — Match Detail black screen + expand predictions + logo/flag fallbacks
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-h1-h2-${TS}"
TARBALL="${1:-/tmp/hotfix_h1_h2_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== HOTFIX H1+H2 Deploy ==="
mkdir -p "${BACKUP}"
cd "${APP}"

git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
if [ -d "${FRONTEND_DIST}" ]; then
  tar czf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" "$(basename "${FRONTEND_DIST}")"
fi
cp -a worldcup_predictor/api/routes/predictions.py "${BACKUP}/predictions.py" 2>/dev/null || true
cp -a worldcup_predictor/api/match_center_helpers.py "${BACKUP}/match_center_helpers.py" 2>/dev/null || true
cp -a worldcup_predictor/api/display_helpers.py "${BACKUP}/display_helpers.py" 2>/dev/null || true

echo "=== Extract ==="
tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r$//' scripts/deploy_hotfix_h1_h2_production.sh scripts/deploy_hotfix_h1_h2_smoke.sh scripts/validate_hotfix_h1_match_detail_logo_flags.py 2>/dev/null || true
chmod +x scripts/deploy_hotfix_h1_h2_smoke.sh 2>/dev/null || true

echo "=== Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== Restart API ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active --quiet worldcup-api

echo "=== Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== Validate ==="
SKIP_FRONTEND_BUILD=1 "${APP}/.venv/bin/python" "${APP}/scripts/validate_hotfix_h1_match_detail_logo_flags.py" | tee "${BACKUP}/validate_h1.log"

echo "=== Smoke ==="
bash scripts/deploy_hotfix_h1_h2_smoke.sh | tee "${BACKUP}/smoke.log"

echo "DEPLOY_OK commit=$(cat "${BACKUP}/pre_deploy_commit.txt") backup=${BACKUP}"
