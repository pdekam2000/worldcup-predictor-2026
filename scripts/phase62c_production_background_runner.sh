#!/usr/bin/env bash
# Phase 62C — production-safe background launcher for Phase 62B
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/worldcup-predictor}"
LOG_PATH="${LOG_PATH:-/tmp/phase62b.log}"
MAX_SM_CALLS="${MAX_SM_CALLS:-200}"
PYTHON="${PYTHON:-$APP_ROOT/.venv/bin/python}"
SCRIPT="$APP_ROOT/scripts/phase62b_sportmonks_wc_xg_lineups_completion.py"

cd "$APP_ROOT"

if [[ ! -f .env.production ]]; then
  echo "ERROR: .env.production not found in $APP_ROOT" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source ./.env.production
set +a

echo "[phase62c] inspecting partial outputs before launch..."
ls -lh data/validation/phase62b_progress.json 2>/dev/null || echo "  (no checkpoint yet)"
ls -lh data/validation/phase62b_mapping_audit.json 2>/dev/null || echo "  (no mapping audit yet)"
ls -lh data/validation/phase62b_sportmonks_wc_completion.json 2>/dev/null || echo "  (no completion artifact yet)"
du -sh data/egie/world_cup/raw 2>/dev/null || true

CMD="$PYTHON $SCRIPT --max-sm-calls $MAX_SM_CALLS --progress-every 5"
echo "[phase62c] launching: nohup $CMD > $LOG_PATH 2>&1 &"
nohup $PYTHON "$SCRIPT" --max-sm-calls "$MAX_SM_CALLS" --progress-every 5 > "$LOG_PATH" 2>&1 &
PID=$!

echo "PID=$PID"
echo "LOG_PATH=$LOG_PATH"
echo "COMMAND=nohup $PYTHON $SCRIPT --max-sm-calls $MAX_SM_CALLS --progress-every 5 > $LOG_PATH 2>&1 &"
echo ""
echo "Monitor:"
echo "  tail -f $LOG_PATH"
echo "  ps aux | grep phase62b"
echo "  pgrep -af phase62b"
echo "  du -sh data/"
echo "  ls -lh data/validation/"
