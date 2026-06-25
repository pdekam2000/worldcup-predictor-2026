#!/usr/bin/env bash
# Phase A9B — controlled production deploy with full backup.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/sites-enabled/worldcup}"
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase-a9b-deploy-${TS}"

echo "=== Phase A9B Production Deploy ==="
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
cp -a /etc/nginx/nginx.conf "${BACKUP}/nginx.conf" 2>/dev/null || true

if command -v pg_dump >/dev/null 2>&1 && [ -f .env.production ]; then
  set -a && source .env.production && set +a
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres_dump.sql" 2>/dev/null || echo "pg_dump skipped"
  fi
fi

mkdir -p "${BACKUP}/runtime"
cp -a data/shadow/*.jsonl "${BACKUP}/runtime/" 2>/dev/null || true
cp -a data/enterprise/*.json "${BACKUP}/runtime/" 2>/dev/null || true

echo "=== 2. Fetch and sync ==="
git fetch origin
TARGET="${A9B_TARGET_REF:-origin/main}"
git stash push -u -m "phase-a9b-pre-deploy-${TS}" || true
git checkout main
git reset --hard "${TARGET}"

echo "=== 3. Restore runtime data ==="
mkdir -p data/shadow data/enterprise
RUNTIME_STASH="${BACKUP}/runtime"
cp -a "${RUNTIME_STASH}/"*.jsonl data/shadow/ 2>/dev/null || true
cp -a data/enterprise/*.json data/enterprise/ 2>/dev/null || true
chown -R www-data:www-data data/enterprise 2>/dev/null || true

echo "=== 4. Build frontend ==="
cd "${APP}/base44-d"
npm run build
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}"

echo "=== 5. Restart services ==="
systemctl restart worldcup-api
sleep 4
nginx -t && systemctl reload nginx

echo "=== 6. API smoke ==="
BASE="${SMOKE_BASE:-https://footballpredictor.it.com}"
for path in \
  "/api/health" \
  "/api/competitions" \
  "/api/matches?competition=all&include_summary=true&page_size=5&status=upcoming"; do
  code=$(curl -sS -o /tmp/a9b_smoke.json -w "%{http_code}" "${BASE}${path}")
  echo "${path} => ${code}"
  if [ "${code}" != "200" ]; then
    head -c 400 /tmp/a9b_smoke.json || true
    echo ""
  fi
done

echo "=== 7. Frontend route smoke (shell) ==="
for path in /login /matches /combo-tips /dashboard; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" "${BASE}${path}")
  echo "${path} => ${code}"
done

echo "deploy_head=$(git -C ${APP} rev-parse HEAD)"
echo "backup=${BACKUP}"
echo "=== DONE ==="
