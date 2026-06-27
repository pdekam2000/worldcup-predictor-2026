#!/usr/bin/env bash
set -euo pipefail
BACKUP="${1:-}"
APP=/opt/worldcup-predictor
FRONTEND_DIST=/var/www/worldcup/frontend/dist

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
.venv/bin/python scripts/validate_hotfix_pack3_evaluated_visibility.py | tee "${BACKUP}/validate.log"

echo "SMOKE /api/results/evaluated"
curl -sf "http://127.0.0.1:8000/api/results/evaluated?range=all&limit=10" | head -c 400
echo
echo "DEPLOY_OK backup=${BACKUP}"
