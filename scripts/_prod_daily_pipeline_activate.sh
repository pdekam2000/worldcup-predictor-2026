#!/usr/bin/env bash
# Activate daily prediction lifecycle on production and enable schedules.
set -euo pipefail

APP=/opt/worldcup-predictor
TARGET_SHA="${1:-origin/main}"
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/daily-pipeline-activate-${TS}"

cd "${APP}"

echo "=== PRE-DEPLOY ==="
PRE_SHA=$(git rev-parse HEAD)
echo "PRE_SHA=${PRE_SHA}"
git fetch origin
git rev-parse HEAD
git rev-parse origin/main

echo "=== BACKUP ==="
mkdir -p "${BACKUP}"
echo "${PRE_SHA}" > "${BACKUP}/pre_deploy_commit.txt"
cp -a .env.production "${BACKUP}/" 2>/dev/null || true
for u in worldcup-prediction-daily worldcup-results-hourly worldcup-odds-refresh worldcup-forward-evaluation; do
  cp -a "/etc/systemd/system/${u}.service" "${BACKUP}/" 2>/dev/null || true
  cp -a "/etc/systemd/system/${u}.timer" "${BACKUP}/" 2>/dev/null || true
done

echo "=== DEPLOY CODE ==="
git reset --hard "${TARGET_SHA}"
DEPLOYED_SHA=$(git rev-parse HEAD)
echo "DEPLOYED_SHA=${DEPLOYED_SHA}"

# Confirm daily pipeline package present
test -f worldcup_predictor/owner_daily/pipeline/orchestrator.py
test -f scripts/run_daily_prediction_freeze_evaluation_pipeline.py
test -f scripts/run_production_prediction_pipeline.py

echo "=== INSTALL SYSTEMD UNITS ==="
cp -f deployment/systemd/worldcup-prediction-daily.service /etc/systemd/system/
cp -f deployment/systemd/worldcup-prediction-daily.timer /etc/systemd/system/
cp -f deployment/systemd/worldcup-results-hourly.service /etc/systemd/system/
cp -f deployment/systemd/worldcup-results-hourly.timer /etc/systemd/system/
cp -f deployment/systemd/worldcup-odds-refresh.service /etc/systemd/system/
cp -f deployment/systemd/worldcup-odds-refresh.timer /etc/systemd/system/
cp -f deployment/systemd/worldcup-forward-evaluation.service /etc/systemd/system/
cp -f deployment/systemd/worldcup-forward-evaluation.timer /etc/systemd/system/
systemctl daemon-reload

echo "=== ENABLE TIMERS ==="
systemctl enable --now worldcup-prediction-daily.timer
systemctl enable --now worldcup-results-hourly.timer
systemctl enable --now worldcup-odds-refresh.timer
systemctl enable --now worldcup-forward-evaluation.timer

echo "=== RESTART SERVICES ==="
systemctl restart worldcup-api worldcup-gpt-actions worldcup-mcp
sleep 4
systemctl is-active worldcup-api worldcup-gpt-actions worldcup-mcp

echo "=== TIMER STATUS ==="
systemctl is-enabled worldcup-prediction-daily.timer worldcup-results-hourly.timer worldcup-odds-refresh.timer worldcup-forward-evaluation.timer
systemctl list-timers --all | grep -E 'worldcup-prediction-daily|worldcup-results-hourly|worldcup-odds-refresh|worldcup-forward-evaluation' || true

echo "=== SMOKE: module import ==="
sudo -u www-data env APP_ENV=production PYTHONPATH="${APP}" bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   .venv/bin/python -c \"
from worldcup_predictor.owner_daily.pipeline import run_daily_pipeline, DailyPipelineConfig
from worldcup_predictor.owner.production_pipeline.runner import run_production_prediction_pipeline
print('PIPELINE_IMPORT_OK')
print('DEPLOYED_SHA', '${DEPLOYED_SHA}')
\""

echo "=== SMOKE: GPT Actions report endpoint ==="
curl -sS -o /tmp/daily_pipeline_report_smoke.json -w "http=%{http_code}\n" \
  "https://footballpredictor.it.com/api/gpt-actions/v1/system/status" || true
head -c 400 /tmp/daily_pipeline_report_smoke.json || true
echo

echo "DEPLOY_OK ${DEPLOYED_SHA}"
echo "DAILY_PIPELINE_PRODUCTION_ACTIVE_AND_SCHEDULED"
