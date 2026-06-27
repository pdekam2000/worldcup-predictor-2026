#!/usr/bin/env bash
# Phase A12 — Prediction Archive & Accuracy Center Pro
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase-a12-${TS}"
TARBALL="${1:-/tmp/phase_a12_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase A12 Deploy ==="
mkdir -p "${BACKUP}"
cd "${APP}"

git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
if [ -d "${FRONTEND_DIST}" ]; then
  cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
fi

echo "=== Extract tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

echo "=== Frontend build ==="
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true

echo "=== Restart API ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active --quiet worldcup-api

echo "=== Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== Smoke ==="
bash scripts/deploy_phase_a12_smoke.sh
echo "DEPLOY_OK"
