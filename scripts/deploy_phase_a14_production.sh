#!/usr/bin/env bash
# Phase A14 — Background Prediction Prefetch Engine
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase-a14-${TS}"
TARBALL="${1:-/tmp/phase_a14_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase A14 Deploy ==="
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

echo "=== Install prefetch systemd timer ==="
cp "${APP}/deployment/systemd/worldcup-prediction-prefetch.service" /etc/systemd/system/
cp "${APP}/deployment/systemd/worldcup-prediction-prefetch.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable worldcup-prediction-prefetch.timer
systemctl start worldcup-prediction-prefetch.service || true

echo "=== Restart API ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active --quiet worldcup-api

echo "=== Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== Smoke ==="
bash "${APP}/scripts/deploy_phase_a14_smoke.sh"
echo "DEPLOY_OK"
