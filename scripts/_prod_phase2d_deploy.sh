#!/usr/bin/env bash
# Phase 2D — Controlled production deploy (fast-forward origin/main only)
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase2d-result-eval-deploy-${TS}"

cd "${APP}"

echo "=== PRE-DEPLOY AUDIT ==="
PRE_SHA=$(git rev-parse HEAD)
echo "PRE_SHA=${PRE_SHA}"
git fetch origin
ORIGIN_SHA=$(git rev-parse origin/main)
echo "ORIGIN_SHA=${ORIGIN_SHA}"

echo "=== TABLE COUNTS (pre) ==="
sqlite3 data/football_intelligence.db "SELECT 'fixture_results', COUNT(*) FROM fixture_results;"
sqlite3 data/evaluation/forward_prediction_tracking.db "SELECT 'frozen_predictions', COUNT(*) FROM frozen_predictions;"
sqlite3 data/evaluation/forward_prediction_tracking.db "SELECT 'actual_results', COUNT(*) FROM actual_results;"
sqlite3 data/evaluation/forward_prediction_tracking.db "SELECT 'market_evaluations', COUNT(*) FROM market_evaluations;"

echo "=== BACKUP ==="
mkdir -p "${BACKUP}"
echo "${PRE_SHA}" > "${BACKUP}/pre_deploy_commit.txt"
echo "${ORIGIN_SHA}" > "${BACKUP}/origin_main_commit.txt"
sqlite3 data/football_intelligence.db ".backup '${BACKUP}/football_intelligence.db'"
cp -a data/evaluation/forward_prediction_tracking.db "${BACKUP}/forward_prediction_tracking.db"
cp -a .env.production "${BACKUP}/" 2>/dev/null || true

echo "=== FAST-FORWARD DEPLOY ==="
git reset --hard origin/main
DEPLOYED_SHA=$(git rev-parse HEAD)
echo "DEPLOYED_SHA=${DEPLOYED_SHA}"

echo "=== EVAL SCHEMA (additive Phase 2D) ==="
sudo -u www-data env APP_ENV=production PYTHONPATH="${APP}" bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   python3 -c \"
from worldcup_predictor.forward_evaluation.db import connect_eval_db, schema_column_names
c = connect_eval_db()
cols = schema_column_names(c)
for col in ('result_quality_status','result_content_hash','eligibility_class','evaluation_version'):
    print(col, col in cols)
c.close()
\""

echo "=== RESTART SERVICES ==="
systemctl restart worldcup-api worldcup-gpt-actions worldcup-mcp
sleep 4
systemctl is-active worldcup-api worldcup-gpt-actions worldcup-mcp

echo "DEPLOY_OK ${DEPLOYED_SHA}"
