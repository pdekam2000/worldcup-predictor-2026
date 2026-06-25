#!/usr/bin/env bash
# Phase 60A — full production push: Elite Shadow GUI + comparison + admin modules
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase60a-full-gui-shadow-${TS}"
TARBALL="${1:-/tmp/phase60a_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase 60A Full GUI + Shadow Deploy ==="
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
if [ -f /etc/nginx/sites-enabled/worldcup ]; then
  cp -a /etc/nginx/sites-enabled/worldcup "${BACKUP}/nginx_worldcup.conf" 2>/dev/null || true
fi
tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/deps.py \
  worldcup_predictor/api/routes/admin_elite_shadow.py \
  worldcup_predictor/admin/elite_shadow_preview.py \
  worldcup_predictor/admin/elite_shadow_comparison.py \
  worldcup_predictor/database/repository.py \
  base44-d/src/App.jsx \
  base44-d/src/pages/EliteShadowPreview.jsx \
  base44-d/src/lib/navConfig.js \
  base44-d/src/api/saasApi.js \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

echo "=== 3. Surgical frontend patches (preserve server App.jsx) ==="
git checkout HEAD -- base44-d/src/App.jsx base44-d/src/lib/navConfig.js 2>/dev/null || true
python3 scripts/apply_phase60a_server_patch.py
chmod +x scripts/deploy_phase60a_smoke.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase60a_smoke.sh scripts/apply_phase60a_server_patch.py scripts/validate_phase60a_full_deploy.py 2>/dev/null || true
chown -R www-data:www-data "${APP}/worldcup_predictor" "${APP}/data/shadow" 2>/dev/null || true
chmod -R u+rwX,g+rwX "${APP}/data/shadow" 2>/dev/null || true

echo "=== 4. Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== 5. Restart API ==="
systemctl restart worldcup-api
sleep 6
if ! systemctl is-active --quiet worldcup-api; then
  echo "API_FAILED — rolling back snapshot"
  tar xzf "${BACKUP}/repo_snapshot_pre.tar.gz" -C "${APP}" 2>/dev/null || true
  systemctl restart worldcup-api || true
  echo "ROLLED_BACK_API"
  exit 1
fi
systemctl status worldcup-api --no-pager | head -20
journalctl -u worldcup-api -n 30 --no-pager || true

echo "=== 6. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 7. Smoke ==="
bash scripts/deploy_phase60a_smoke.sh 2>&1 | tee "${BACKUP}/smoke_60a.log"

git rev-parse HEAD > "${BACKUP}/post_deploy_commit.txt" 2>/dev/null || true
echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
