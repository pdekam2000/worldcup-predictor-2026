#!/usr/bin/env bash
# Phase 33 + 33B production deploy — backup, overlay, restart, manual auto-cycle test
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase33-33b-${TS}"
TARBALL="${1:-/tmp/phase33_33b_deploy.tar.gz}"

echo "=== Phase 33 + 33B Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
tar czf "${BACKUP}/repo_overlay_pre.tar.gz" \
  worldcup_predictor/automation/worldcup_background \
  worldcup_predictor/api/pick_visibility.py \
  worldcup_predictor/api/market_ranking_engine.py \
  worldcup_predictor/api/prediction_output.py \
  worldcup_predictor/api/routes/predictions.py \
  worldcup_predictor/database/migrations.py \
  worldcup_predictor/database/repository.py \
  worldcup_predictor/config/settings.py \
  worldcup_predictor/orchestration/predict_pipeline.py \
  worldcup_predictor/quota/prediction_cache.py \
  worldcup_predictor/quota/cache_policy.py \
  main.py \
  deployment/systemd/worldcup-daily-predict.service \
  deployment/systemd/worldcup-daily-predict.timer \
  deployment/systemd/worldcup-evaluate-results.service \
  deployment/systemd/worldcup-evaluate-results.timer \
  deployment/systemd/worldcup-auto-cycle.service \
  deployment/systemd/worldcup-auto-cycle.timer \
  scripts/validate_phase33_background_prediction_evaluation.py \
  scripts/validate_phase33b_no_bet_ux_replacement.py \
  2>/dev/null || true

echo "Extracting ${TARBALL}..."
tar xzf "${TARBALL}" -C "${APP}"

# Frontend dist if included
if [ -d "${APP}/_deploy_frontend_dist" ]; then
  cp -a "${APP}/_deploy_frontend_dist/." /var/www/worldcup/frontend/dist/
  rm -rf "${APP}/_deploy_frontend_dist"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor/automation" 2>/dev/null || true
chown www-data:www-data "${APP}/data/football_intelligence.db" 2>/dev/null || true
chmod 664 "${APP}/data/football_intelligence.db" 2>/dev/null || true

echo "Restarting worldcup-api..."
systemctl restart worldcup-api
sleep 3
systemctl is-active worldcup-api

echo "Running migrations via app init..."
sudo -u www-data bash -lc "cd ${APP} && .venv/bin/python -c \"from worldcup_predictor.database.repository import FootballIntelligenceRepository; FootballIntelligenceRepository()\""

echo "=== Manual auto-cycle test ==="
sudo -u www-data bash -lc "cd ${APP} && .venv/bin/python main.py worldcup-auto-cycle" | tee "${BACKUP}/auto_cycle.log"

echo "=== Health check ==="
curl -sf http://127.0.0.1:8000/api/health | head -c 500
echo ""

echo "=== Stored predictions count ==="
sudo -u www-data bash -lc "cd ${APP} && .venv/bin/python -c \"
from worldcup_predictor.database.repository import FootballIntelligenceRepository
r = FootballIntelligenceRepository()
print('stored', r.count_worldcup_stored_predictions())
summary = r.get_worldcup_accuracy_summary()
print('accuracy_summary', bool(summary))
\""

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
