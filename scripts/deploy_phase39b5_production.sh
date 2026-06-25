#!/usr/bin/env bash
# Phase 39B-5 — production deploy: Stripe billing (39B-1..4) + 41A/41B
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase39b5-${TS}"
TARBALL="${1:-/tmp/phase39b5_deploy.tar.gz}"
STRIPE_ENV_FILE="${2:-/root/.wcp_stripe_env}"

echo "=== Phase 39B-5 Production Deploy (Stripe Billing) ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
chown www-data:www-data "${BACKUP}" 2>/dev/null || chmod 775 "${BACKUP}"

cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
echo "Pre-deploy commit: $(cat "${BACKUP}/pre_deploy_commit.txt")"

if [ -f data/football_intelligence.db ]; then
  cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db"
  echo "SQLite backed up"
fi

if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/"
  echo "Frontend dist backed up"
fi

if [ -f .env.production ]; then
  echo "$(readlink -f .env.production 2>/dev/null || realpath .env.production 2>/dev/null || echo "${APP}/.env.production")" > "${BACKUP}/env_production_path.txt"
fi

if [ -f /etc/systemd/system/worldcup-api.service ]; then
  cp -a /etc/systemd/system/worldcup-api.service "${BACKUP}/worldcup-api.service"
fi

set -a
# shellcheck disable=SC1091
source .env.production 2>/dev/null || true
set +a

if [ -n "${DATABASE_URL:-}" ] && command -v pg_dump >/dev/null 2>&1; then
  pg_dump "${DATABASE_URL}" -Fc -f "${BACKUP}/postgres.dump" 2>/dev/null && echo "PostgreSQL backed up" || echo "PostgreSQL backup skipped"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes \
  worldcup_predictor/billing \
  worldcup_predictor/subscription \
  requirements.txt \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
  echo "Frontend deployed"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true
chown www-data:www-data "${APP}/data/football_intelligence.db" 2>/dev/null || true
chmod 664 "${APP}/data/football_intelligence.db" 2>/dev/null || true
mkdir -p "${APP}/data/logs" "${APP}/data/backups"
chown -R www-data:www-data "${APP}/data/logs" "${APP}/data/backups" 2>/dev/null || true

echo "=== 3. Python deps (stripe) ==="
bash -lc "cd ${APP} && .venv/bin/pip install -q 'stripe>=8.0.0'" \
  2>&1 | tee "${BACKUP}/pip_stripe.log" | tail -5
chown -R www-data:www-data "${APP}/.venv" 2>/dev/null || true

echo "=== 4. Stripe env (non-secret defaults + optional secrets file) ==="
ENV_FILE="${APP}/.env.production"
touch "${ENV_FILE}"
_set_env() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >> "${ENV_FILE}"
  fi
}

_set_env "APP_PUBLIC_URL" "https://footballpredictor.it.com"
_set_env "STRIPE_SUCCESS_URL" "https://footballpredictor.it.com/billing/success"
_set_env "STRIPE_CANCEL_URL" "https://footballpredictor.it.com/billing/cancel"
_set_env "STRIPE_PORTAL_RETURN_URL" "https://footballpredictor.it.com/subscription"
_set_env "STRIPE_MODE" "test"

if [ -f "${STRIPE_ENV_FILE}" ]; then
  echo "Merging Stripe secrets from ${STRIPE_ENV_FILE} (values not logged)"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      \#*|"") continue ;;
      STRIPE_*=*)
        key="${line%%=*}"
        val="${line#*=}"
        _set_env "$key" "$val"
        ;;
    esac
  done < "${STRIPE_ENV_FILE}"
  echo "stripe_secrets_merged=yes"
else
  echo "stripe_secrets_merged=no (create ${STRIPE_ENV_FILE} with STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, price IDs)"
fi

chmod 640 "${ENV_FILE}" 2>/dev/null || true
chown www-data:www-data "${ENV_FILE}" 2>/dev/null || true

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/audit_stripe_production_env.py" \
  2>&1 | tee "${BACKUP}/stripe_env_audit_pre_migrate.log" || true

echo "=== 5. Alembic migration ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -m alembic upgrade head" \
  2>&1 | tee "${BACKUP}/alembic_upgrade.log"

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -m alembic current" \
  2>&1 | tee "${BACKUP}/alembic_current.log"

echo "=== 6. Restart services ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
systemctl is-active nginx

_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

echo "=== 7. Validations ==="
_run_validation scripts/audit_stripe_production_env.py 2>&1 | tee "${BACKUP}/stripe_env_audit.log" || true
_run_validation scripts/validate_phase39b1_stripe_foundation.py 2>&1 | tee "${BACKUP}/validate_39b1.log" | tail -20 || true
_run_validation scripts/validate_phase39b2_stripe_checkout.py 2>&1 | tee "${BACKUP}/validate_39b2.log" | tail -20 || true
_run_validation scripts/validate_phase39b3_stripe_webhooks.py 2>&1 | tee "${BACKUP}/validate_39b3.log" | tail -20 || true
_run_validation scripts/validate_phase39b4_billing_dashboard.py 2>&1 | tee "${BACKUP}/validate_39b4.log" | tail -20 || true
_run_validation scripts/validate_phase41b_auth_hardening.py 2>&1 | tee "${BACKUP}/validate_41b.log" | tail -15 || true
_run_validation scripts/validate_phase41a_smtp_email_operations.py 2>&1 | tee "${BACKUP}/validate_41a.log" | tail -15 || true
_run_validation scripts/validate_phase40a_auth_user_management.py 2>&1 | tee "${BACKUP}/validate_40a.log" | tail -15 || true

echo "=== 8. Health + billing routes ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""
echo -n "billing_readiness_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/billing/readiness || echo "000"
echo -n "billing_webhook_no_sig: "
curl -sf -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/billing/webhook -d '{}' || echo "000"

if [ -f scripts/deploy_phase39b5_smoke.sh ]; then
  bash scripts/deploy_phase39b5_smoke.sh 2>&1 | tee "${BACKUP}/live_smoke.log" || true
fi

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
