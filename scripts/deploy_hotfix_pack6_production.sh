#!/usr/bin/env bash
# Hotfix Pack 6 — production deploy (results visibility)
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/hotfix-pack6-${TS}"
TARBALL="${1:-/tmp/hotfix_pack6_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

mkdir -p "${BACKUP}"
cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
if [ -d "${FRONTEND_DIST}" ]; then
  tar czf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" "$(basename "${FRONTEND_DIST}")"
fi

tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r$//' scripts/_remote_deploy_hotfix_pack6.sh scripts/validate_hotfix_pack6_results_visibility.py 2>/dev/null || true
bash scripts/_remote_deploy_hotfix_pack6.sh "${BACKUP}"
