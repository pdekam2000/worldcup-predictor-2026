#!/usr/bin/env bash
# HOTFIX — Email verification on register — production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-email-verification-${TS}"
TARBALL="${1:-/tmp/hotfix_email_verification_deploy.tar.gz}"

echo "=== HOTFIX Email Verification Register Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"

if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/routes/auth.py \
  worldcup_predictor/api/web_auth.py \
  worldcup_predictor/auth/email_verification.py \
  worldcup_predictor/notifications/email_delivery.py \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  rm -rf "${FRONTEND:?}/"*
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true

echo "=== 4. Email config audit (no secrets) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.notifications.diagnostics import email_diagnostics
s = get_settings()
d = email_diagnostics(s)
print('smtp_host_set', bool((s.smtp_host or '').strip()))
print('smtp_user_set', bool((s.smtp_user or '').strip()))
print('smtp_password_set', bool((s.smtp_password or '').strip()))
print('smtp_from_set', bool((s.smtp_from or '').strip()))
print('smtp_configured', d['smtp_configured'])
print('email_operations_ready', d['email_operations_ready'])
PY" | tee "${BACKUP}/email_config_audit.log"

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   .venv/bin/python scripts/validate_hotfix_email_verification_register.py --api-only" \
  2>&1 | tee "${BACKUP}/validate_hotfix.log" | tail -40

echo "=== 6. Smoke ==="
bash scripts/deploy_hotfix_email_verification_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
