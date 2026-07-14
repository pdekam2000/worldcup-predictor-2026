#!/usr/bin/env bash
# Phase 2C — Tier B structured persistence production deploy
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase2c-tier-b-persistence-${TS}"

cd "${APP}"

echo "=== PRE-DEPLOY ==="
PRE_SHA=$(git rev-parse HEAD)
echo "PRE_SHA=${PRE_SHA}"
UNTRACKED_COUNT=$(git status --short | wc -l | tr -d ' ')
echo "UNTRACKED_COUNT=${UNTRACKED_COUNT}"

echo "=== BACKUP ==="
mkdir -p "${BACKUP}"
echo "${PRE_SHA}" > "${BACKUP}/pre_deploy_commit.txt"
sqlite3 data/football_intelligence.db ".backup '${BACKUP}/football_intelligence.db'"
cp -a data/evaluation/forward_prediction_tracking.db "${BACKUP}/" 2>/dev/null || true
cp -a .env.production "${BACKUP}/" 2>/dev/null || true

echo "=== FETCH + FF DEPLOY ==="
git fetch origin
git reset --hard origin/main
DEPLOYED_SHA=$(git rev-parse HEAD)
echo "DEPLOYED_SHA=${DEPLOYED_SHA}"

echo "=== MIGRATION (additive Phase 2C columns) ==="
sudo -u www-data env APP_ENV=production PYTHONPATH="${APP}" bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && \
   ${APP}/.venv/bin/python -c \"
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.config.settings import get_settings
s = get_settings()
c = connect(s.sqlite_path)
ensure_schema_compat(c)
cols = [r[1] for r in c.execute('PRAGMA table_info(worldcup_stored_predictions)').fetchall()]
print('wsp_has_prediction_scope', 'prediction_scope' in cols)
c.commit()
c.close()
\""

echo "=== RESTART SERVICES ==="
systemctl restart worldcup-api worldcup-gpt-actions worldcup-mcp
sleep 4
systemctl is-active worldcup-api worldcup-gpt-actions worldcup-mcp

echo "DEPLOY_OK ${DEPLOYED_SHA}"
