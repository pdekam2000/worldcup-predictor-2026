#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/hotfix-pack7-${TS}"
mkdir -p "${BACKUP}"
cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
tar xzf /tmp/hotfix_pack7_deploy.tar.gz -C "${APP}"
sed -i 's/\r$//' scripts/_remote_deploy_hotfix_pack7.sh scripts/validate_hotfix_pack7_owner_dashboard.py 2>/dev/null || true
bash scripts/_remote_deploy_hotfix_pack7.sh "${BACKUP}"
