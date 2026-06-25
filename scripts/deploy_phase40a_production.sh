#!/usr/bin/env bash
# Phase 40A — production deploy: auth user management
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase40a-${TS}"
TARBALL="${1:-/tmp/phase40a_deploy.tar.gz}"
OWNER_EMAIL="${2:-kamangar.pedram@gmail.com}"

echo "=== Phase 40A Production Deploy (Auth User Management) ==="
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

# Pre-reset user table export (separate from reset script backup)
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
import json
from pathlib import Path
from sqlalchemy import text
from worldcup_predictor.database.saas_factory import saas_uow

backup = Path('${BACKUP}')
tables = ['users', 'user_settings', 'subscriptions', 'user_favorites', 'user_alerts', 'user_notifications', 'user_prediction_history']
manifest = {}
with saas_uow() as uow:
    for table in tables:
        try:
            rows = uow.session.execute(text(f'SELECT row_to_json(t) FROM {table} AS t')).fetchall()
            payload = [r[0] for r in rows]
            (backup / f'pre_reset_{table}.json').write_text(json.dumps(payload, default=str, indent=2), encoding='utf-8')
            manifest[table] = len(payload)
        except Exception as exc:
            manifest[table] = f'error:{exc}'
(backup / 'pre_reset_user_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('pre_reset_user_export_ok', json.dumps(manifest))
PY" 2>&1 | tee "${BACKUP}/pre_reset_export.log"

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/api/web_auth.py \
  worldcup_predictor/api/routes/auth.py \
  worldcup_predictor/database/postgres/models.py \
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
mkdir -p "${APP}/data/logs" "${APP}/data/dev" "${APP}/data/backups"
chown -R www-data:www-data "${APP}/data/logs" "${APP}/data/dev" "${APP}/data/backups" 2>/dev/null || true

echo "=== 3. Alembic migration ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -m alembic upgrade head" \
  2>&1 | tee "${BACKUP}/alembic_upgrade.log"

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python -m alembic current" \
  2>&1 | tee "${BACKUP}/alembic_current.log"

echo "=== 4. Owner seed (secure password — not logged) ==="
OWNER_PW_FILE="/root/.wcp_phase40a_owner_initial.txt"
if [ -z "${OWNER_INITIAL_PASSWORD:-}" ]; then
  openssl rand -base64 24 > "${OWNER_PW_FILE}"
  chmod 600 "${OWNER_PW_FILE}"
  chown root:root "${OWNER_PW_FILE}"
  export OWNER_INITIAL_PASSWORD="$(cat "${OWNER_PW_FILE}")"
  echo "OWNER_INITIAL_PASSWORD=generated (stored root-only at ${OWNER_PW_FILE})"
else
  echo "OWNER_INITIAL_PASSWORD=provided via session env (not logged)"
fi

RESET_LOG="${BACKUP}/reset_seed.log"
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production OWNER_INITIAL_PASSWORD="${OWNER_INITIAL_PASSWORD}" bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/reset_users_seed_owner.py --confirm-reset-users --email '${OWNER_EMAIL}' --plan pro" \
  2>&1 | tee "${RESET_LOG}" | grep -v -i password || true

unset OWNER_INITIAL_PASSWORD

echo "=== 5. Restart services ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
systemctl is-active nginx

_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

echo "=== 6. Validations ==="
_run_validation scripts/validate_phase40a_auth_user_management.py 2>&1 | tee "${BACKUP}/validate_phase40a.log" | tail -35
_run_validation scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a.log" | tail -12 || true
_run_validation scripts/validate_phase38a_subscription_system.py 2>&1 | tee "${BACKUP}/validate_phase38a.log" | tail -12 || true
_run_validation scripts/validate_phase39a_commercial_readiness.py 2>&1 | tee "${BACKUP}/validate_phase39a.log" | tail -15 || true
_run_validation scripts/validate_phase39a_hotfix_ui_dashboard.py 2>&1 | tee "${BACKUP}/validate_hotfix.log" | tail -20 || true

echo "=== 7. Health ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo "=== 8. Owner status (no secrets) ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
import json
from worldcup_predictor.database.saas_factory import saas_uow

email = '${OWNER_EMAIL}'.strip().lower()
with saas_uow() as uow:
    u = uow.users.get_by_email(email)
    sub = uow.subscriptions.get_for_user(u.id) if u else None
    print(json.dumps({
        'owner_exists': u is not None,
        'email': email,
        'role': u.role.value if u else None,
        'email_verified': u.email_verified if u else None,
        'is_banned': u.is_banned if u else None,
        'plan': sub.plan.value if sub else None,
        'total_users': len(uow.users.list_users(limit=500)),
    }, indent=2))
PY" 2>&1 | tee "${BACKUP}/owner_status.json"

echo "BACKUP_PATH=${BACKUP}"
echo "OWNER_PW_FILE=${OWNER_PW_FILE}"
echo "DEPLOY_OK"
