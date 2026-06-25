#!/usr/bin/env bash
# Phase 52E — Hybrid confidence API + UI production deploy
set -euo pipefail

APP="${APP_ROOT:-/var/www/worldcup}"
BACKUP_TAG="phase52e_$(date +%Y%m%d_%H%M%S)"
BACKUP="${APP}/backups/${BACKUP_TAG}"

echo "=== Phase 52E deploy — hybrid confidence API + UI ==="
mkdir -p "${BACKUP}"

echo "Backup..."
cp -a "${APP}/worldcup_predictor" "${BACKUP}/worldcup_predictor"
cp -a "${APP}/base44-d/dist" "${BACKUP}/frontend_dist" 2>/dev/null || true
cp -a "${APP}/alembic/versions" "${BACKUP}/alembic_versions" 2>/dev/null || true

cd "${APP}"
git pull --ff-only || true

echo "Alembic migration 010..."
source .venv/bin/activate 2>/dev/null || true
alembic upgrade head

echo "Validate Phase 52E..."
python scripts/validate_phase52e_hybrid_confidence_api_ui.py

echo "Build frontend..."
cd base44-d
npm ci
npm run build
cd ..

echo "Restart API..."
systemctl restart worldcup-api
sleep 2
systemctl is-active worldcup-api

echo "Reload nginx..."
nginx -t && systemctl reload nginx

echo "Smoke checks..."
curl -sf "http://127.0.0.1:8000/api/goal-timing/picks?limit=1" | head -c 500
echo ""
curl -sf "http://127.0.0.1:8000/api/goal-timing/dashboard" | head -c 500
echo ""

echo "PHASE_52E_STATUS=PRODUCTION_ACTIVE"
