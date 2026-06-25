#!/usr/bin/env bash
# Phase 47C — production deploy: Rule A conditional harmonization
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase47c-${TS}"
TARBALL="${1:-/tmp/phase47c_deploy.tar.gz}"

echo "=== Phase 47C Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
chmod +x scripts/deploy_phase47c_production.sh scripts/phase47c_production_smoke.py 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase47c_production.sh scripts/validate_phase47c_conditional_harmonization.py scripts/phase47c_production_smoke.py 2>/dev/null || true

# Ensure Rule A active in production env
if grep -q '^RULE_A_GATE_MODE=' .env.production 2>/dev/null; then
  sed -i 's/^RULE_A_GATE_MODE=.*/RULE_A_GATE_MODE=active/' .env.production
else
  echo 'RULE_A_GATE_MODE=active' >> .env.production
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 4. Reload nginx ==="
nginx -t
systemctl reload nginx

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase47c_conditional_harmonization.py" \
  2>&1 | tee "${BACKUP}/validate_47c.log" | tail -40

echo "=== 6. Production smoke ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/phase47c_production_smoke.py" \
  2>&1 | tee "${BACKUP}/smoke_47c.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
