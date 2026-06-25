#!/usr/bin/env bash
# Phase 39A-HOTFIX — production deploy: UI + dashboard hotfix
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase39a-hotfix-${TS}"
TARBALL="${1:-/tmp/phase39a_hotfix_deploy.tar.gz}"

echo "=== Phase 39A-HOTFIX Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

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
  worldcup_predictor/api/routes/user.py \
  base44-d/src/components/ui/use-toast.jsx \
  base44-d/src/components/ui/toaster.jsx \
  base44-d/src/components/ui/toast.jsx \
  base44-d/src/pages/SettingsPage.jsx \
  base44-d/src/pages/MatchCenter.jsx \
  base44-d/src/components/match/MatchVersusCenter.jsx \
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
mkdir -p "${APP}/data/logs"
chown -R www-data:www-data "${APP}/data/logs" 2>/dev/null || true

echo "=== 3. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
systemctl is-active nginx

_run_validation() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python $1"
}

echo "=== 4. Validations ==="
_run_validation scripts/validate_phase39a_hotfix_ui_dashboard.py 2>&1 | tee "${BACKUP}/validate_hotfix.log" | tail -30
_run_validation scripts/validate_phase39a_commercial_readiness.py 2>&1 | tee "${BACKUP}/validate_phase39a.log" | tail -20
_run_validation scripts/validate_phase38a_subscription_system.py 2>&1 | tee "${BACKUP}/validate_phase38a.log" | tail -15 || true
_run_validation scripts/validate_phase37a_admin_security.py 2>&1 | tee "${BACKUP}/validate_phase37a.log" | tail -12 || true

echo "=== 5. Health ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo "=== 6. Hotfix API smoke ==="
echo -n "dashboard_unauth: "
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/user/dashboard || echo "000"

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python - <<'PY'
import uuid
from fastapi.testclient import TestClient
from worldcup_predictor.api.main import app
from worldcup_predictor.api.web_auth import WebAuthUser, issue_access_token
from worldcup_predictor.database.saas_factory import saas_uow

email = f'hotfix-smoke-{uuid.uuid4().hex[:8]}@test.local'
with saas_uow() as uow:
    row = uow.users.create(email=email, full_name='Hotfix Smoke')
    uid = row.id
token = issue_access_token(WebAuthUser(id=str(uid), email=email, full_name='Hotfix Smoke', role='user'))
client = TestClient(app)
h = {'Authorization': f'Bearer {token}'}
r = client.get('/api/user/dashboard', headers=h)
assert r.status_code == 200, r.text
assert r.json().get('status') == 'ok'
r2 = client.patch('/api/user/settings', headers=h, json={'language': 'en', 'timezone': 'UTC'})
assert r2.status_code == 200, r2.text
print('hotfix_api_smoke_ok dashboard=200 settings=200')
PY" 2>&1 | tee "${BACKUP}/smoke_hotfix_api.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
