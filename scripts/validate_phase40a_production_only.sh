#!/usr/bin/env bash
set -uo pipefail
APP=/opt/worldcup-predictor
BACKUP="${APP}/backups/deploy-phase40a-20260620-185613"

_run() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source ${APP}/.env.production && set +a && ${APP}/.venv/bin/python $1"
}

_run scripts/validate_phase40a_auth_user_management.py 2>&1 | tee "${BACKUP}/validate_phase40a_final.log" | tail -40
_run scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a_final.log" | tail -8
_run scripts/validate_phase38a_subscription_system.py 2>&1 | tee "${BACKUP}/validate_phase38a_final.log" | tail -8
_run scripts/validate_phase39a_commercial_readiness.py 2>&1 | tee "${BACKUP}/validate_phase39a_final.log" | tail -10
_run scripts/validate_phase39a_hotfix_ui_dashboard.py 2>&1 | tee "${BACKUP}/validate_hotfix_final.log" | tail -15

curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health_final.json"
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
        'is_banned': u.is_banned if u else None,
        'plan': sub.plan.value if sub else None,
        'total_users': len(uow.users.list_users(limit=500)),
    }, indent=2))
PY" | tee "${BACKUP}/owner_status_final.json"

sed -i 's/\r$//' "${APP}/scripts/deploy_phase40a_smoke.sh"
bash "${APP}/scripts/deploy_phase40a_smoke.sh" https://footballpredictor.it.com 2>&1 | tee "${BACKUP}/smoke_final.log"

echo "FINAL_OK"
