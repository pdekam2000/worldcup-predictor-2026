#!/usr/bin/env bash
# Deploy frozen league batch prediction/evaluation + IMPLEMENT-1 automation to production.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
cd "${APP}"
export APP_ENV=production

echo "=== PRE-DEPLOY ==="
PRE_HEAD=$(git rev-parse HEAD)
echo "pre_commit=${PRE_HEAD}"
df -h / /opt 2>/dev/null | tail -2 || df -h / | tail -1
systemctl is-active worldcup-api nginx 2>/dev/null || true
curl -sf http://127.0.0.1:8000/api/health >/dev/null && echo "api_health=ok" || echo "api_health=fail"

echo "=== DB CONNECTIVITY ==="
.venv/bin/python -c "
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
s = get_settings()
c = connect(s.sqlite_path)
print('sqlite_ok', c.execute('SELECT 1').fetchone()[0])
c.close()
"

echo "=== GIT PULL ==="
git fetch origin main
git pull --ff-only origin main
POST_HEAD=$(git rev-parse HEAD)
ORIGIN_HEAD=$(git rev-parse origin/main)
echo "post_commit=${POST_HEAD}"
echo "origin_main=${ORIGIN_HEAD}"

echo "=== SCHEMA (safe) ==="
.venv/bin/python -c "
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.migrations import ensure_schema_compat
ensure_schema_compat(FootballIntelligenceRepository()._conn)
from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import ensure_batch_tables
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
ensure_batch_tables(connect(get_settings().sqlite_path))
print('schema_ok')
"

REQ_CHANGED=0
if git diff --name-only "${PRE_HEAD}" "${POST_HEAD}" | grep -qE 'requirements.*\.txt|pyproject\.toml'; then
  REQ_CHANGED=1
fi
if [[ "${REQ_CHANGED}" -eq 1 ]]; then
  echo "=== REQUIREMENTS CHANGED — pip install ==="
  .venv/bin/pip install -r requirements.txt -q
else
  echo "requirements_unchanged=skip_pip"
fi

echo "=== COMPILE ==="
.venv/bin/python -m compileall worldcup_predictor/owner_predict_eval worldcup_predictor/owner/production_pipeline -q

echo "=== RESTART API ==="
systemctl restart worldcup-api
sleep 3
systemctl is-active worldcup-api
nginx -t && systemctl reload nginx

echo "=== IMPLEMENT-1 TIMERS ==="
if [[ -f scripts/install_implement1_production_timers.sh ]]; then
  bash scripts/install_implement1_production_timers.sh || true
fi
if systemctl is-enabled worldcup-evaluate-results.timer >/dev/null 2>&1; then
  echo "phase44a_eval_timer=enabled"
else
  if [[ -f scripts/install_phase44a_eval_timer.sh ]]; then
    bash scripts/install_phase44a_eval_timer.sh || true
  fi
fi

echo "=== BATCH SNAPSHOT COUNTS ==="
.venv/bin/python -c "
import json, sqlite3
from worldcup_predictor.config.settings import get_settings
s = get_settings()
c = sqlite3.connect(s.sqlite_path)
c.row_factory = sqlite3.Row
def q(sql, args=()):
    return c.execute(sql, args).fetchall()
frozen = q('SELECT COUNT(*) n FROM owner_league_batch_snapshots WHERE is_frozen=1')
evals = q('SELECT COUNT(*) n FROM owner_league_batch_evaluations')
waiting = q(\"\"\"
  SELECT COUNT(*) n FROM owner_league_batch_snapshots s
  LEFT JOIN owner_league_batch_evaluations e ON s.batch_id=e.batch_id AND s.fixture_id=e.fixture_id
  WHERE s.is_frozen=1 AND (e.fixture_id IS NULL OR json_extract(e.evaluation_json,'$.evaluation_status')!='EVALUATED')
\"\"\")
segments = q('SELECT competition_type, COUNT(*) n FROM owner_league_batch_snapshots WHERE is_frozen=1 GROUP BY competition_type')
batches = q('SELECT batch_id, COUNT(*) n FROM owner_league_batch_snapshots WHERE is_frozen=1 GROUP BY batch_id')
print(json.dumps({
  'frozen_snapshots': frozen[0]['n'] if frozen else 0,
  'completed_evaluations': evals[0]['n'] if evals else 0,
  'waiting_evaluations': waiting[0]['n'] if waiting else 0,
  'segments': {r['competition_type']: r['n'] for r in segments},
  'batches': {r['batch_id']: r['n'] for r in batches},
}, indent=2))
c.close()
" 2>/dev/null || echo "batch_tables_not_yet_populated"

echo "=== SMOKE ==="
curl -sf http://127.0.0.1:8000/api/health && echo
curl -sf http://127.0.0.1:8000/api/version && echo

echo "=== TIMERS ==="
systemctl list-timers --all | grep -E 'worldcup-(prediction-daily|results-hourly|evaluate-results|auto-cycle|daily-predict)' || true

if [[ "${POST_HEAD}" == "${ORIGIN_HEAD}" ]]; then echo "HEADS_MATCH=yes"; else echo "HEADS_MATCH=no"; fi
echo "deploy_complete"
