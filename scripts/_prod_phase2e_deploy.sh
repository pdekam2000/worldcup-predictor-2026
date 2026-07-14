#!/usr/bin/env bash
# Phase 2E — Controlled production deploy (scheduler units disabled)
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase2e-scheduler-${TS}"

cd "${APP}"

echo "=== PRE-DEPLOY ==="
PRE_SHA=$(git rev-parse HEAD)
echo "PRE_SHA=${PRE_SHA}"
git fetch origin
ORIGIN_SHA=$(git rev-parse origin/main)
echo "ORIGIN_SHA=${ORIGIN_SHA}"

echo "=== TIMER STATE (pre) ==="
systemctl is-enabled worldcup-forward-evaluation.timer 2>/dev/null || echo "timer_not_installed"
systemctl is-active worldcup-forward-evaluation.timer 2>/dev/null || echo "timer_inactive_or_missing"

echo "=== BACKUP ==="
mkdir -p "${BACKUP}"
echo "${PRE_SHA}" > "${BACKUP}/pre_deploy_commit.txt"
sqlite3 data/football_intelligence.db ".backup '${BACKUP}/football_intelligence.db'"
cp -a data/evaluation/forward_prediction_tracking.db "${BACKUP}/"

echo "=== FAST-FORWARD ==="
git reset --hard origin/main
DEPLOYED_SHA=$(git rev-parse HEAD)
echo "DEPLOYED_SHA=${DEPLOYED_SHA}"

echo "=== INSTALL SYSTEMD (disabled) ==="
cp deployment/systemd/worldcup-forward-evaluation.service /etc/systemd/system/
cp deployment/systemd/worldcup-forward-evaluation.timer /etc/systemd/system/
systemctl daemon-reload
# Explicitly ensure NOT enabled
systemctl disable worldcup-forward-evaluation.timer 2>/dev/null || true
systemctl stop worldcup-forward-evaluation.timer 2>/dev/null || true

echo "=== EVAL SCHEMA ==="
sudo -u www-data env APP_ENV=production PYTHONPATH="${APP}" bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   python3 -c \"from worldcup_predictor.forward_evaluation.db import connect_eval_db; c=connect_eval_db(); print('forward_evaluation_runs', c.execute('SELECT name FROM sqlite_master WHERE name=\\\"forward_evaluation_runs\\\"').fetchone()); c.close()\""

echo "=== TIMER STATE (post) ==="
systemctl is-enabled worldcup-forward-evaluation.timer || true
systemctl is-active worldcup-forward-evaluation.timer || true
systemctl is-active worldcup-api worldcup-gpt-actions worldcup-mcp

echo "DEPLOY_OK ${DEPLOYED_SHA}"
