#!/bin/bash
set -eu
cd /opt/worldcup-predictor

pkill -f 'sqlite3 data/football_intelligence' 2>/dev/null || true
systemctl stop worldcup-api || true
sleep 2

BKP="backups/db/football_intelligence_pre_sync3_final.db"
mkdir -p backups/db backups/source_sync
rm -f "$BKP"
echo "=== DB BACKUP -> $BKP ==="
sqlite3 data/football_intelligence.db ".backup '$BKP'"
ls -lh "$BKP"
sqlite3 "$BKP" "PRAGMA integrity_check;"

echo "=== KEY COUNTS ==="
sqlite3 data/football_intelligence.db <<'SQL'
SELECT 'fixtures', COUNT(*) FROM fixtures;
SELECT 'fixture_results', COUNT(*) FROM fixture_results;
SELECT 'worldcup_stored_predictions', COUNT(*) FROM worldcup_stored_predictions;
SELECT 'ecse_prediction_snapshots', COUNT(*) FROM ecse_prediction_snapshots;
SELECT 'ecse_prediction_evaluations', COUNT(*) FROM ecse_prediction_evaluations;
SQL

git diff HEAD -- worldcup_predictor/ scripts/ base44-d/ > backups/source_sync/full_project_sync_3_production_source.patch 2>/dev/null || true
git checkout HEAD -- worldcup_predictor/ scripts/ base44-d/ migrations/ 2>/dev/null || true
git clean -fd -- worldcup_predictor/ scripts/ 2>/dev/null || true

git fetch origin main
git pull --ff-only origin main
echo "HEAD=$(git rev-parse HEAD)"
echo "ORIGIN=$(git rev-parse origin/main)"

sqlite3 data/football_intelligence.db "PRAGMA table_info(fixture_results);" | grep regulation || true

export APP_ENV=production
export PYTHONPATH=/opt/worldcup-predictor
.venv/bin/python -m compileall worldcup_predictor scripts 2>&1 | tail -3
.venv/bin/python scripts/validate_result_truth_repair_1.py 2>&1 | tail -3
.venv/bin/python scripts/validate_result_truth_schema_v8_and_ecse_reevaluation_1.py 2>&1 | tail -3
.venv/bin/python scripts/validate_next_3_upcoming_match_predictions_1.py 2>&1 | tail -3

systemctl start worldcup-api
sleep 2
systemctl is-active worldcup-api
curl -s http://127.0.0.1:8000/api/health
echo
echo SYNC3_COMPLETE
