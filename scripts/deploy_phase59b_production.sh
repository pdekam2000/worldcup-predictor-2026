#!/usr/bin/env bash
# Phase 59B — owner-only soft launch: Elite Shadow Preview
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase59b-${TS}"
TARBALL="${1:-/tmp/phase59b_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase 59B Owner Soft Launch Deploy ==="
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
tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/admin_elite_shadow.py \
  worldcup_predictor/admin/elite_shadow_preview.py \
  base44-d/src/App.jsx \
  base44-d/src/pages/EliteShadowPreview.jsx \
  base44-d/src/lib/navConfig.js \
  base44-d/src/api/saasApi.js \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball (backend + shadow data) ==="
tar xzf "${TARBALL}" -C "${APP}" \
  worldcup_predictor/admin/elite_shadow_preview.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/admin_elite_shadow.py \
  worldcup_predictor/api/routes/admin_gate.py \
  worldcup_predictor/api/routes/admin_accuracy.py \
  base44-d/src/pages/EliteShadowPreview.jsx \
  data/shadow/elite_orchestrator_predictions.jsonl \
  data/shadow/elite_orchestrator_evaluations.jsonl \
  data/shadow/root_cause_store/knowledge_records.jsonl \
  scripts/validate_phase59b_owner_soft_launch.py \
  scripts/apply_phase59b_server_patch.py \
  scripts/deploy_phase59b_smoke.sh

cd "${APP}"
git checkout HEAD -- base44-d/src/App.jsx base44-d/src/lib/navConfig.js base44-d/src/api/saasApi.js 2>/dev/null || true
python3 scripts/apply_phase59b_server_patch.py
chmod +x scripts/deploy_phase59b_smoke.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase59b_smoke.sh scripts/validate_phase59b_owner_soft_launch.py scripts/apply_phase59b_server_patch.py 2>/dev/null || true
chown -R www-data:www-data "${APP}/worldcup_predictor" "${APP}/data/shadow" 2>/dev/null || true
chmod -R u+rwX,g+rwX "${APP}/data/shadow" 2>/dev/null || true

echo "=== 3. Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== 4. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 5. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 6. Smoke ==="
bash scripts/deploy_phase59b_smoke.sh 2>&1 | tee "${BACKUP}/smoke_59b.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
