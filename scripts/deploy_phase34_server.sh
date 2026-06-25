#!/usr/bin/env bash
# Phase 34 production deploy — Admin Accuracy + Learning + Subscription
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase34-${TS}"
TARBALL="${1:-/tmp/phase34_deploy.tar.gz}"

echo "=== Phase 34 Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

# 1. Record pre-deploy commit
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
echo "Pre-deploy commit: $(cat "${BACKUP}/pre_deploy_commit.txt")"

# 2. SQLite snapshot
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true

# 3. Frontend dist snapshot
if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/" 2>/dev/null || true
fi

# 4. Repo overlay snapshot (Phase 34 touched paths)
tar czf "${BACKUP}/repo_overlay_pre.tar.gz" \
  worldcup_predictor/admin \
  worldcup_predictor/subscription \
  worldcup_predictor/api/routes/admin_accuracy.py \
  worldcup_predictor/api/main.py \
  worldcup_predictor/api/routes/predictions.py \
  worldcup_predictor/api/routes/user.py \
  worldcup_predictor/database/migrations.py \
  worldcup_predictor/database/repository.py \
  2>/dev/null || true

echo "Extracting ${TARBALL}..."
tar xzf "${TARBALL}" -C "${APP}"

# Frontend dist
if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
fi

# Permissions
chown -R www-data:www-data "${APP}/worldcup_predictor/admin" 2>/dev/null || true
chown -R www-data:www-data "${APP}/worldcup_predictor/subscription" 2>/dev/null || true
chown www-data:www-data "${APP}/data/football_intelligence.db" 2>/dev/null || true
chmod 664 "${APP}/data/football_intelligence.db" 2>/dev/null || true

# 5. Schema init (PHASE45 tables: learning_reports, user_daily_prediction_usage)
echo "Running SQLite schema init..."
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python -c \"
from worldcup_predictor.database.repository import FootballIntelligenceRepository
r = FootballIntelligenceRepository()
tables = ['learning_reports', 'user_daily_prediction_usage', 'worldcup_stored_predictions']
for t in tables:
    row = r._conn.execute(\\\"SELECT 1 FROM sqlite_master WHERE type='table' AND name=?\\\", (t,)).fetchone()
    print(t, 'OK' if row else 'MISSING')
\"" | tee "${BACKUP}/schema_init.log"

echo "Restarting worldcup-api..."
systemctl restart worldcup-api
sleep 4
systemctl is-active worldcup-api

echo "=== Health check ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo "=== Public health ==="
curl -sf https://footballpredictor.it.com/api/health | head -c 300 || curl -sf http://127.0.0.1:8000/api/health
echo ""

echo "=== Phase 34 validation ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase34_admin_accuracy_learning_subscription.py" 2>&1 | tee "${BACKUP}/validate_phase34.log" | tail -5

echo "=== Phase 33 regression ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase33_background_prediction_evaluation.py" 2>&1 | tee "${BACKUP}/validate_phase33.log" | tail -5

echo "=== Phase 33B regression ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase33b_no_bet_ux_replacement.py" 2>&1 | tee "${BACKUP}/validate_phase33b.log" | tail -5

echo "=== Admin routes smoke ==="
curl -sf -o /dev/null -w "admin_accuracy_summary HTTP %{http_code}\n" http://127.0.0.1:8000/api/admin/accuracy/summary || true

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
