#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
BACKUP="${APP}/backups/deploy-phase40a-20260620-185613"

export OWNER_INITIAL_PASSWORD="$(cat /root/.wcp_phase40a_owner_initial.txt)"
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production OWNER_INITIAL_PASSWORD="${OWNER_INITIAL_PASSWORD}" \
  bash -lc "cd ${APP} && set -a && source ${APP}/.env.production && set +a && ${APP}/.venv/bin/python scripts/reset_users_seed_owner.py --confirm-reset-users --email kamangar.pedram@gmail.com --plan pro" \
  2>&1 | grep -v -i password | tee "${BACKUP}/reset_seed_retry.log"
unset OWNER_INITIAL_PASSWORD

systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api

_run() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source ${APP}/.env.production && set +a && ${APP}/.venv/bin/python $1"
}

_run scripts/validate_phase40a_auth_user_management.py 2>&1 | tee "${BACKUP}/validate_phase40a_retry.log" | tail -40
_run scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a_retry.log" | tail -8
_run scripts/validate_phase38a_subscription_system.py 2>&1 | tee "${BACKUP}/validate_phase38a_retry.log" | tail -8
_run scripts/validate_phase39a_commercial_readiness.py 2>&1 | tee "${BACKUP}/validate_phase39a_retry.log" | tail -10
_run scripts/validate_phase39a_hotfix_ui_dashboard.py 2>&1 | tee "${BACKUP}/validate_hotfix_retry.log" | tail -15

curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health_retry.json"
echo ""

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source ${APP}/.env.production && set +a && ${APP}/.venv/bin/python - <<'PY'
import json
from worldcup_predictor.database.saas_factory import saas_uow
email = 'kamangar.pedram@gmail.com'
with saas_uow() as uow:
    u = uow.users.get_by_email(email)
    sub = uow.subscriptions.get_for_user(u.id) if u else None
    print(json.dumps({
        'owner_exists': u is not None,
        'role': u.role.value if u else None,
        'email_verified': u.email_verified if u else None,
        'plan': sub.plan.value if sub else None,
        'total_users': len(uow.users.list_users(limit=500)),
    }, indent=2))
PY" | tee "${BACKUP}/owner_status_retry.json"

sed -i 's/\r$//' "${APP}/scripts/deploy_phase40a_smoke.sh"
bash "${APP}/scripts/deploy_phase40a_smoke.sh" https://footballpredictor.it.com 2>&1 | tee "${BACKUP}/smoke.log"

echo "FINISH_OK"
