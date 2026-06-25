#!/usr/bin/env bash
# Phase 44B-D hardening sprint — production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase44-hardening-${TS}"
TARBALL="${1:-/tmp/phase44_hardening_deploy.tar.gz}"

echo "=== Phase 44 Hardening Sprint Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production" 2>/dev/null || true
if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
fi

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"
chmod +x scripts/deploy_phase44_hardening_smoke.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase44_hardening_production.sh scripts/deploy_phase44_hardening_smoke.sh 2>/dev/null || true

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || true

echo "=== 5. Validation (44B + storage on server) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase44b_silent_failure.py" \
  | tee "${BACKUP}/validate_44b.log" | tail -25

echo "=== 6. Smoke ==="
bash scripts/deploy_phase44_hardening_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "=== 7. Stripe env audit (no secrets) ==="
.venv/bin/python scripts/audit_stripe_production_env.py 2>&1 | tee "${BACKUP}/stripe_audit.log" || true

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
