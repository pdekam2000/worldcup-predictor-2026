#!/usr/bin/env bash
# Phase 63 — enterprise platform deploy
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase63-${TS}"
TARBALL="${1:-/tmp/phase63_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase 63 Deploy ==="
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
[ -d "${FRONTEND_DIST}" ] && cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
if command -v pg_dump >/dev/null 2>&1 && [ -f .env.production ]; then
  set -a; source .env.production; set +a
  [ -n "${DATABASE_URL:-}" ] && pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres_pre.sql" 2>/dev/null || true
fi

echo "=== 2. Extract ==="
tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r$//' scripts/migrate_phase63_enterprise_roles.py scripts/ensure_owner_account.py scripts/deploy_phase63_smoke.sh 2>/dev/null || true

echo "=== 3. Role migration + owner ==="
set -a; [ -f .env.production ] && source .env.production; set +a
PYTHON="${APP}/.venv/bin/python3"
[ -x "${PYTHON}" ] || PYTHON=python3
"${PYTHON}" scripts/migrate_phase63_enterprise_roles.py || echo "WARN: migration"
"${PYTHON}" scripts/ensure_owner_account.py || echo "WARN: owner ensure"

echo "=== 4. Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== 5. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 6. Nginx ==="
nginx -t && systemctl reload nginx

echo "=== 7. Smoke ==="
chmod +x scripts/deploy_phase63_smoke.sh 2>/dev/null || true
PHASE63_BASE_URL=https://footballpredictor.it.com bash scripts/deploy_phase63_smoke.sh | tee "${BACKUP}/smoke_63.log"
echo "DONE backup=${BACKUP}"
