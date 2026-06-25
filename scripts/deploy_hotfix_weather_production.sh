#!/usr/bin/env bash
# Hotfix — weather config mismatch production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-hotfix-weather-${TS}"
TARBALL="${1:-/tmp/hotfix_weather_deploy.tar.gz}"

echo "=== Hotfix Weather Config Deploy ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"

cd "${APP}"
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/config/provider_readiness.py \
  worldcup_predictor/api/routes/health.py \
  worldcup_predictor/api/display_helpers.py \
  worldcup_predictor/api/routes/predictions.py \
  worldcup_predictor/intelligence/weather_intelligence_engine.py \
  2>/dev/null || true

tar xzf "${TARBALL}" -C "${APP}"
chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/validate_hotfix_weather_config_mismatch.py" \
  2>&1 | tee "${BACKUP}/validate.log" | tail -20

bash scripts/deploy_hotfix_weather_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"
echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
