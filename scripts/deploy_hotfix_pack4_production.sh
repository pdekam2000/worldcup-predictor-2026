#!/usr/bin/env bash
# Hotfix Pack 4 — production deploy (app version badge)
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/hotfix-pack4-${TS}"
TARBALL="${1:-/tmp/hotfix_pack4_deploy.tar.gz}"
FRONTEND_DIST=/var/www/worldcup/frontend/dist

mkdir -p "${BACKUP}"
cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
if [ -d "${FRONTEND_DIST}" ]; then
  tar czf "${BACKUP}/frontend_dist_pre.tar.gz" -C "$(dirname "${FRONTEND_DIST}")" "$(basename "${FRONTEND_DIST}")"
fi

tar xzf "${TARBALL}" -C "${APP}"
sed -i 's/\r//g' scripts/_remote_deploy_hotfix_pack4.sh scripts/validate_hotfix_pack4_app_version_badge.py scripts/sync_app_version_metadata.py 2>/dev/null || true
bash scripts/_remote_deploy_hotfix_pack4.sh "${BACKUP}"
