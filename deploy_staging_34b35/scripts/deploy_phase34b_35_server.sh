#!/usr/bin/env bash
# Phase 34B + Phase 35 production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase34b-35-${TS}"
TARBALL="${1:-/tmp/phase34b_35_deploy.tar.gz}"

echo "=== Phase 34B + 35 Production Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"

git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
echo "Pre-deploy commit: $(cat "${BACKUP}/pre_deploy_commit.txt")"

cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true

if [ -d "${FRONTEND}" ]; then
  mkdir -p "${BACKUP}/frontend_dist"
  cp -a "${FRONTEND}/." "${BACKUP}/frontend_dist/" 2>/dev/null || true
fi

tar czf "${BACKUP}/repo_overlay_pre.tar.gz" \
  worldcup_predictor/prediction/engine_versions.py \
  worldcup_predictor/automation/worldcup_background/stale_prediction_policy.py \
  worldcup_predictor/api/prediction_metadata.py \
  worldcup_predictor/admin/accuracy_optimization.py \
  worldcup_predictor/admin/learning_engine.py \
  worldcup_predictor/api/routes/admin_accuracy.py \
  2>/dev/null || true

echo "Extracting ${TARBALL}..."
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true
chown www-data:www-data "${APP}/data/football_intelligence.db" 2>/dev/null || true
chmod 664 "${APP}/data/football_intelligence.db" 2>/dev/null || true

echo "Restarting worldcup-api..."
systemctl restart worldcup-api
sleep 4
systemctl is-active worldcup-api

echo "=== Health ==="
curl -sf http://127.0.0.1:8000/api/health | tee "${BACKUP}/health.json"
echo ""

echo "=== Phase 34B validation ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase34b_stale_confidence_cache_fix.py" 2>&1 | tee "${BACKUP}/validate_phase34b.log" | tail -8

echo "=== Phase 35 validation ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase35_accuracy_driven_optimization.py" 2>&1 | tee "${BACKUP}/validate_phase35.log" | tail -8

echo "=== Phase 33 regression ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase33_background_prediction_evaluation.py" 2>&1 | tee "${BACKUP}/validate_phase33.log" | tail -5

echo "=== Phase 33B regression ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase33b_no_bet_ux_replacement.py" 2>&1 | tee "${BACKUP}/validate_phase33b.log" | tail -5

echo "=== Phase 34 regression ==="
sudo -u www-data env PYTHONPATH="${APP}" bash -lc "cd ${APP} && .venv/bin/python scripts/validate_phase34_admin_accuracy_learning_subscription.py" 2>&1 | tee "${BACKUP}/validate_phase34.log" | tail -5

echo "=== Fixture 1489393 force refresh smoke ==="
curl -sf -X POST "http://127.0.0.1:8000/api/predict/1489393?force_refresh=true" -H "Authorization: Bearer SKIP" 2>/dev/null | head -c 200 || echo "(auth required for POST — manual admin refresh)"

echo "=== Admin learning smoke ==="
curl -sf -o /dev/null -w "admin_learning HTTP %{http_code}\n" "http://127.0.0.1:8000/api/admin/learning/dashboard" || true

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
