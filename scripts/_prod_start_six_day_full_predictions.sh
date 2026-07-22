#!/usr/bin/env bash
# Deploy six-day prediction scripts and start background run as www-data.
set -euo pipefail
ROOT=/opt/worldcup-predictor
cd "$ROOT"

for f in \
  scripts/run_six_day_full_predictions_20260722_20260727.py \
  scripts/validate_six_day_full_predictions_20260722_20260727.py \
  scripts/run_owner_full_day_predictions.py
do
  if [[ -f "/tmp/$(basename "$f")" ]]; then
    cp "/tmp/$(basename "$f")" "$ROOT/$f"
    sed -i 's/\r$//' "$ROOT/$f"
    chown www-data:www-data "$ROOT/$f"
  fi
done

mkdir -p "$ROOT/artifacts/six_day_predictions/2026-07-22_2026-07-27" \
         "$ROOT/artifacts/daily_pipeline" \
         "$ROOT/reports/owner/daily" \
         "$ROOT/logs"
chown -R www-data:www-data "$ROOT/artifacts/six_day_predictions" "$ROOT/reports/owner/daily" || true
# ensure daily_pipeline writable
chown -R www-data:www-data "$ROOT/artifacts/daily_pipeline" 2>/dev/null || true

LOG="$ROOT/logs/six_day_full_predictions_20260722_20260727.log"
nohup sudo -u www-data env APP_ENV=production ENVIRONMENT=production ENV_FILE="$ROOT/.env.production" \
  "$ROOT/.venv/bin/python3" "$ROOT/scripts/run_six_day_full_predictions_20260722_20260727.py" \
  >"$LOG" 2>&1 &
echo "PID=$!"
echo "LOG=$LOG"
sleep 2
head -n 40 "$LOG" || true
