#!/usr/bin/env bash
set -euo pipefail
cd /opt/worldcup-predictor
export APP_ENV=production

echo "=== PRE-PULL HEAD ==="
PRE_HEAD=$(git rev-parse HEAD)
echo "$PRE_HEAD"

mkdir -p backups/source_sync data/backups
git diff > backups/source_sync/full_project_sync_2_production_source.patch || true
echo "$PRE_HEAD" > data/backups/pre_full_project_sync_2_commit.txt

echo "=== DB COUNTS ==="
.venv/bin/python scripts/inspect_controlled_knockout_predictions_2.py 2>/dev/null | .venv/bin/python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('production_counts',{}), indent=2)); print('colombia_hash_check: run validate_match_eval')"

echo "=== RESET TRACKED SOURCE DRIFT ==="
git checkout -- worldcup_predictor scripts || true

echo "=== FETCH AND PULL ==="
git fetch origin main
git log --oneline HEAD..origin/main | head -5
git pull --ff-only origin main

POST_HEAD=$(git rev-parse HEAD)
ORIGIN_HEAD=$(git rev-parse origin/main)
echo "POST_HEAD=$POST_HEAD"
echo "ORIGIN_HEAD=$ORIGIN_HEAD"

echo "=== REMOVE STRAY ROOT COPIES ==="
rm -f freshness_refresh.py predictions.py sync_wc_upcoming_fixtures.py validate_eval_coverage_1.py validate_match_eval_1567310_1.py || true
rm -f 'C:UserskamanDesktoppostgres_backup.sql' || true

echo "=== COMPILEALL ==="
.venv/bin/python -m compileall worldcup_predictor scripts 2>&1 | tail -3 || true

echo "=== PRODUCTION VALIDATORS ==="
for v in validate_match_eval_1567310_1.py validate_controlled_knockout_predictions_2.py validate_odds_freshness_1.py validate_odds_timestamp_normalization_1.py validate_owner_predictions_ui_2_end_result_display.py validate_fixture_sync_1.py; do
  echo "-- $v --"
  .venv/bin/python scripts/$v 2>&1 | tail -3 || true
done

echo "=== FRONTEND BUILD ==="
if [ -d base44-d ]; then
  (cd base44-d && npm run build 2>&1 | tail -5)
fi

echo "=== RESTART API ==="
systemctl restart worldcup-api
sleep 2
systemctl is-active worldcup-api || true
systemctl is-active nginx || true

echo "=== SMOKE ==="
curl -s http://127.0.0.1:8000/api/health || true
echo
curl -s http://127.0.0.1:8000/api/version || true
echo

echo "=== TIMERS ==="
for t in worldcup-daily.timer worldcup-hourly.timer owner-daily.timer; do
  systemctl is-enabled "$t" 2>/dev/null || echo "$t n/a"
done

if [ "$POST_HEAD" = "$ORIGIN_HEAD" ]; then echo "HEADS_MATCH=yes"; else echo "HEADS_MATCH=no"; fi
