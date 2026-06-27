#!/usr/bin/env bash
# HOTFIX — Disable email verification requirement — production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-disable-email-verification-${TS}"
TARBALL="${1:-/tmp/hotfix_disable_email_verification_deploy.tar.gz}"
ENV_FILE="${APP}/.env.production"

echo "=== HOTFIX Disable Email Verification Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"

if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
fi

if [ -f "${ENV_FILE}" ]; then
  cp -a "${ENV_FILE}" "${BACKUP}/env.production"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/config/settings.py \
  worldcup_predictor/auth/verification_config.py \
  worldcup_predictor/auth/email_verification.py \
  worldcup_predictor/api/web_auth.py \
  worldcup_predictor/api/deps.py \
  worldcup_predictor/api/routes/auth.py \
  worldcup_predictor/notifications/diagnostics.py \
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

echo "=== 3. Set EMAIL_VERIFICATION_REQUIRED=false ==="
touch "${ENV_FILE}"
if grep -q '^EMAIL_VERIFICATION_REQUIRED=' "${ENV_FILE}"; then
  sed -i 's/^EMAIL_VERIFICATION_REQUIRED=.*/EMAIL_VERIFICATION_REQUIRED=false/' "${ENV_FILE}"
else
  echo 'EMAIL_VERIFICATION_REQUIRED=false' >> "${ENV_FILE}"
fi
grep '^EMAIL_VERIFICATION_REQUIRED=' "${ENV_FILE}" | tee "${BACKUP}/env_flag.txt"

echo "=== 4. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   .venv/bin/python scripts/validate_hotfix_disable_email_verification_requirement.py --api-only" \
  2>&1 | tee "${BACKUP}/validate_hotfix.log" | tail -35

echo "=== 6. Smoke ==="
bash scripts/deploy_hotfix_disable_email_verification_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
