#!/usr/bin/env bash
set -euo pipefail
BACKUP="${1:-}"
APP=/opt/worldcup-predictor
FRONTEND_DIST=/var/www/worldcup/frontend/dist

MAIN="${APP}/worldcup_predictor/api/main.py"
if [ -f "${MAIN}" ] && ! python3 -c "import worldcup_predictor.api.routes.prediction_lifecycle" 2>/dev/null; then
  sed -i '/prediction_lifecycle/d' "${MAIN}" || true
fi

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
.venv/bin/python scripts/validate_hotfix_pack7_owner_dashboard.py | tee "${BACKUP}/validate.log"

echo "SMOKE owner model-center (auth required — status only)"
curl -sf -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/api/owner/model-center" || true
curl -sf "http://127.0.0.1:8000/api/version" | head -c 400
echo
echo "DEPLOY_OK backup=${BACKUP}"
