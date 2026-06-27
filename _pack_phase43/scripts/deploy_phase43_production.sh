#!/usr/bin/env bash
# Phase 43 — production deploy: Weather Intelligence
set -euo pipefail

APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase43-${TS}"
TARBALL="${1:-/tmp/phase43_deploy.tar.gz}"

echo "=== Phase 43 Production Deploy (Weather Intelligence) ==="
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
  cp -a .env.production "${BACKUP}/env.production"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/weather_impact.py \
  worldcup_predictor/providers/weather_provider.py \
  worldcup_predictor/agents/specialists/agents.py \
  worldcup_predictor/orchestration/predict_pipeline.py \
  worldcup_predictor/api/routes/predictions.py \
  worldcup_predictor/prediction/scoring_engine.py \
  worldcup_predictor/config/settings.py \
  2>/dev/null || true

echo "=== 2. Weather env check ==="
if grep -q '^WEATHER_API_KEY=' .env.production 2>/dev/null; then
  key_len=$(grep '^WEATHER_API_KEY=' .env.production | cut -d= -f2- | tr -d '\r' | wc -c)
  if [ "${key_len}" -gt 1 ]; then
    echo "WEATHER_API_KEY=present (length=${key_len})"
  else
    echo "WEATHER_API_KEY=empty"
    exit 1
  fi
else
  echo "WEATHER_API_KEY=missing"
  exit 1
fi

echo "=== 3. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

if [ -d "${APP}/_deploy_frontend_dist" ]; then
  mkdir -p "${FRONTEND}"
  rm -rf "${FRONTEND:?}/"*
  cp -a "${APP}/_deploy_frontend_dist/." "${FRONTEND}/"
  chown -R www-data:www-data "${FRONTEND}" 2>/dev/null || true
  rm -rf "${APP}/_deploy_frontend_dist"
  echo "Frontend deployed"
fi

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 4. Restart services ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api
systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
systemctl is-active nginx

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase43_weather_intelligence.py" \
  2>&1 | tee "${BACKUP}/validate_43.log" | tail -25

echo "=== 6. Smoke ==="
bash scripts/deploy_phase43_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
