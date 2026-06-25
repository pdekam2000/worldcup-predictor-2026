#!/usr/bin/env bash
# Phase 62 — full UI rebrand + owner access deploy
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase62-${TS}"
TARBALL="${1:-/tmp/phase62_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase 62 Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
if [ -d "${FRONTEND_DIST}" ]; then
  cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
fi
if command -v pg_dump >/dev/null 2>&1 && [ -f .env.production ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.production
  set +a
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres_pre.sql" 2>/dev/null || true
  fi
fi
tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  base44-d/src/App.jsx \
  base44-d/src/index.css \
  base44-d/src/lib/navConfig.js \
  base44-d/src/components/dashboard/DashboardLayout.jsx \
  base44-d/src/components/layout/SidebarNav.jsx \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

echo "=== 3. Restore compatible App.jsx + surgical patch ==="
PHASE60D_BACKUP="$(ls -td "${APP}"/backups/deploy-phase60d-* 2>/dev/null | head -1 || true)"
if [ -n "${PHASE60D_BACKUP}" ] && [ -f "${PHASE60D_BACKUP}/repo_snapshot_pre.tar.gz" ]; then
  tar xzf "${PHASE60D_BACKUP}/repo_snapshot_pre.tar.gz" base44-d/src/App.jsx -C "${APP}"
  echo "Restored App.jsx from ${PHASE60D_BACKUP}"
fi
rm -rf "${APP}/base44-d/src/components/terminal" 2>/dev/null || true
sed -i 's/\r$//' scripts/apply_phase62_server_patch.py scripts/ensure_owner_super_admin.py scripts/deploy_phase62_smoke.sh 2>/dev/null || true
python3 scripts/apply_phase62_server_patch.py

echo "=== 4. Ensure owner super_admin ==="
set -a
# shellcheck disable=SC1091
[ -f .env.production ] && source .env.production
set +a
PYTHON="${APP}/.venv/bin/python3"
if [ ! -x "${PYTHON}" ]; then PYTHON=python3; fi
"${PYTHON}" scripts/ensure_owner_super_admin.py || echo "WARN: owner ensure skipped"

echo "=== 5. Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== 6. API health (no backend code change expected) ==="
systemctl is-active worldcup-api || systemctl restart worldcup-api
sleep 4
systemctl status worldcup-api --no-pager | head -15

echo "=== 7. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 8. Smoke ==="
chmod +x scripts/deploy_phase62_smoke.sh 2>/dev/null || true
bash scripts/deploy_phase62_smoke.sh 2>&1 | tee "${BACKUP}/smoke_62.log"

echo "=== Phase 62 deploy complete ==="
echo "Backup: ${BACKUP}"
