#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/hotfix-pack8-${TS}"
mkdir -p "${BACKUP}"
cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
tar xzf /tmp/hotfix_pack8_deploy.tar.gz -C "${APP}"
sed -i 's/\r$//' scripts/validate_hotfix_pack8_owner_dashboard.py 2>/dev/null || true
cd "${APP}/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
rsync -a --delete dist/ /var/www/worldcup/frontend/dist/
chown -R www-data:www-data /var/www/worldcup/frontend/dist/ 2>/dev/null || true
systemctl restart worldcup-api
sleep 6
systemctl is-active --quiet worldcup-api
cd "${APP}"
.venv/bin/python scripts/validate_hotfix_pack8_owner_dashboard.py | tee "${BACKUP}/validate.log"
curl -sf "http://127.0.0.1:8000/api/version" | head -c 300
echo
echo "DEPLOY_OK backup=${BACKUP}"
