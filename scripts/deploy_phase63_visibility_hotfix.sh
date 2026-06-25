#!/usr/bin/env bash
# Phase 63 — production visibility hotfix (owner UI + cache bust)
set -euo pipefail
APP=/opt/worldcup-predictor
FRONTEND_DIST=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase63-visibility-${TS}"

echo "=== Phase 63 Visibility Hotfix ==="
mkdir -p "${BACKUP}"
[ -d "${FRONTEND_DIST}" ] && cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true

cd "${APP}"
set -a
# shellcheck disable=SC1091
[ -f .env.production ] && source .env.production
set +a

echo "=== Owner account + token bump ==="
"${APP}/.venv/bin/python3" scripts/ensure_owner_account.py || true
"${APP}/.venv/bin/python3" scripts/bump_owner_token_version.py || true

echo "=== Visibility patch ==="
"${APP}/.venv/bin/python3" scripts/apply_phase63_visibility_hotfix.py 2>/dev/null || true
git checkout HEAD -- base44-d/src/pages/Dashboard.jsx 2>/dev/null || true

echo "=== Frontend rebuild ==="
cd "${APP}/base44-d"
npm run build
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== Nginx no-cache index.html ==="
NGINX_SITE="/etc/nginx/sites-enabled/worldcup"
if [ -f "${NGINX_SITE}" ] && ! grep -q 'location = /index.html' "${NGINX_SITE}"; then
  sed -i '/location \/ {/i\
    location = /index.html {\
        add_header Cache-Control "no-cache, no-store, must-revalidate";\
        add_header Pragma "no-cache";\
        try_files $uri =404;\
    }\
' "${NGINX_SITE}"
fi
nginx -t && systemctl reload nginx

echo "=== Smoke ==="
curl -sf -o /dev/null -w "owner_html=%{http_code}\n" https://footballpredictor.it.com/owner
curl -sf -o /dev/null -w "owner_api=%{http_code}\n" https://footballpredictor.it.com/api/owner/overview
grep -o '/assets/index-[^"]*\.js' "${FRONTEND_DIST}/index.html" || true
echo "DONE backup=${BACKUP}"
