#!/bin/bash
set -eu
cd /opt/worldcup-predictor

echo "=== HARD RESET TO origin/main ==="
git fetch origin main
git reset --hard origin/main
git clean -fd --exclude=data --exclude=backups --exclude=artifacts --exclude=.env --exclude=.venv 2>/dev/null || git clean -fd
echo "HEAD=$(git rev-parse HEAD)"
echo "ORIGIN=$(git rev-parse origin/main)"

export APP_ENV=production
export PYTHONPATH=/opt/worldcup-predictor
.venv/bin/python -m compileall worldcup_predictor scripts 2>&1 | tail -3
.venv/bin/python scripts/validate_result_truth_repair_1.py 2>&1 | tail -5
.venv/bin/python scripts/validate_result_truth_schema_v8_and_ecse_reevaluation_1.py 2>&1 | tail -5
.venv/bin/python scripts/validate_next_3_upcoming_match_predictions_1.py 2>&1 | tail -5

systemctl start worldcup-api || true
sleep 2
systemctl is-active worldcup-api
curl -s http://127.0.0.1:8000/api/health
echo
echo SYNC3_RESET_COMPLETE
