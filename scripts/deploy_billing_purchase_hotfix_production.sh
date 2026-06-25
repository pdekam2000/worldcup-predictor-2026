#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-billing-purchase-${TS}"
TARBALL="${1:-/tmp/billing_purchase_hotfix.tar.gz}"
echo "=== Billing purchase hotfix deploy ==="
mkdir -p "${BACKUP}"
cd "${APP}"
tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/billing/ \
  worldcup_predictor/api/routes/billing.py \
  2>/dev/null || true
tar xzf "${TARBALL}" -C "${APP}"
if [ -d "${APP}/_deploy_frontend_dist" ]; then
  rm -rf "${FRONTEND:?}/"*
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
fi
chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/validate_billing_purchase_error.py" \
  2>&1 | tee "${BACKUP}/validate.log" | tail -25
bash scripts/deploy_billing_purchase_hotfix_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"
echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
