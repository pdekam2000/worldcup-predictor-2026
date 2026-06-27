#!/usr/bin/env bash
# Phase A18 — Paper Betting Simulator
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase-a18-${TS}"
TARBALL="${1:-/tmp/phase_a18_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

echo "=== Phase A18 Deploy ==="
mkdir -p "${BACKUP}"
cd "${APP}"

git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
if [ -f data/football_intelligence.db ]; then
  cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
fi
if command -v pg_dump >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
  pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres.sql" 2>/dev/null || true
fi
if [ -d "${FRONTEND_DIST}" ]; then
  cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
fi
tar czf "${BACKUP}/repo_pre_deploy.tar.gz" --exclude=node_modules --exclude=.git/objects --exclude=base44-d/dist . 2>/dev/null || true

echo "=== Extract tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

echo "=== Run migrations (SQLite schema compat) ==="
cd "${APP}"
.venv/bin/python -c "from worldcup_predictor.database.repository import FootballIntelligenceRepository; from worldcup_predictor.database.migrations import ensure_schema_compat; ensure_schema_compat(FootballIntelligenceRepository()._conn)"

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
bash "${APP}/scripts/deploy_phase_a18_smoke.sh"
echo "DEPLOY_OK"
