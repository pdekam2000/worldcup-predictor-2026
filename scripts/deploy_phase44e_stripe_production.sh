#!/usr/bin/env bash
# Phase 44E — Stripe activation production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase44e-${TS}"

echo "=== Phase 44E Stripe Activation Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/" 2>/dev/null || true
cp -a .env.production "${BACKUP}/env.production.pre"

echo "=== 2. Provision Stripe prices (if needed) ==="
sed -i 's/\r$//' scripts/provision_phase44e_stripe_prices.py 2>/dev/null || true
.venv/bin/python scripts/provision_phase44e_stripe_prices.py --apply | tee "${BACKUP}/provision.log"

echo "=== 2b. Provision Stripe webhook (if needed) ==="
sed -i 's/\r$//' scripts/provision_phase44e_stripe_webhook.py 2>/dev/null || true
.venv/bin/python scripts/provision_phase44e_stripe_webhook.py --apply | tee -a "${BACKUP}/provision.log" || true

echo "=== 3. Restart API ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || true

echo "=== 4. Audit ==="
.venv/bin/python scripts/audit_phase44e_stripe_production.py | tee "${BACKUP}/audit.log"

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase44e_stripe_activation.py" \
  | tee "${BACKUP}/validate.log" | tail -30

echo "=== 6. Smoke ==="
bash scripts/deploy_phase44e_stripe_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
