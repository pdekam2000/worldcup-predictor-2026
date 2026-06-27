#!/usr/bin/env bash
set -euo pipefail
BACKUP="${1:-}"
APP=/opt/worldcup-predictor
FRONTEND_DIST=/var/www/worldcup/frontend/dist

cd "${APP}"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export DEPLOY_COMMIT="${COMMIT}"
python3 scripts/sync_app_version_metadata.py 2>/dev/null || true

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
.venv/bin/python scripts/validate_hotfix_pack4_app_version_badge.py | tee "${BACKUP}/validate.log"

echo "SMOKE /api/version"
curl -sf "http://127.0.0.1:8000/api/version"
echo
echo "DEPLOY_OK backup=${BACKUP} commit=${COMMIT}"
