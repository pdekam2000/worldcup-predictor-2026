#!/usr/bin/env bash
# Phase A10 — Match Center V2 production deploy with full backup.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/sites-enabled/worldcup}"
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase-a10-deploy-${TS}"

echo "=== Phase A10 Production Deploy ==="
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt"
cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
cp -a .env.production "${BACKUP}/.env.production" 2>/dev/null || true
cp -a .env "${BACKUP}/.env" 2>/dev/null || true
if [ -f data/football_intelligence.db ]; then
  cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db"
fi
if [ -f "${NGINX_CONF}" ]; then
  cp -a "${NGINX_CONF}" "${BACKUP}/nginx_worldcup.conf"
fi

echo "=== 2. Fetch and sync ==="
git fetch origin
TARGET="${A10_TARGET_REF:-origin/main}"
git stash push -u -m "phase-a10-pre-deploy-${TS}" || true
git checkout main
git reset --hard "${TARGET}"

echo "=== 3. Build frontend ==="
cd "${APP}/base44-d"
npm run build
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}"

echo "=== 4. Restart services ==="
systemctl restart worldcup-api
sleep 4
nginx -t && systemctl reload nginx

echo "=== 5. API smoke ==="
BASE="${SMOKE_BASE:-https://footballpredictor.it.com}"
for path in \
  "/api/health" \
  "/api/competitions?include_counts=true" \
  "/api/matches?competition=all&include_summary=true&page_size=5&status=upcoming" \
  "/api/matches/elite-picks-today?limit=5"; do
  code=$(curl -sS -o /tmp/a10_smoke.json -w "%{http_code}" "${BASE}${path}")
  echo "${path} => ${code}"
  if [ "${code}" != "200" ]; then
    head -c 400 /tmp/a10_smoke.json || true
    echo ""
  fi
done

echo "=== 6. Frontend route smoke ==="
for path in /login /matches /combo-tips; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" "${BASE}${path}")
  echo "${path} => ${code}"
done

echo "deploy_head=$(git -C ${APP} rev-parse HEAD)"
echo "backup=${BACKUP}"
echo "=== DONE ==="
