#!/usr/bin/env bash
# Phase 62C — finalize and validate after background Phase 62B run
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/worldcup-predictor}"
LOG_PATH="${LOG_PATH:-/tmp/phase62b.log}"
PYTHON="${PYTHON:-$APP_ROOT/.venv/bin/python}"

cd "$APP_ROOT"

set -a
# shellcheck disable=SC1091
source ./.env.production 2>/dev/null || true
set +a

echo "=== Phase 62C finalization check ==="
echo "Log tail:"
tail -n 20 "$LOG_PATH" 2>/dev/null || echo "(no log)"

if pgrep -af phase62b >/dev/null 2>&1; then
  echo "WARNING: phase62b still running"
  pgrep -af phase62b
  exit 2
fi

echo "Running validation..."
"$PYTHON" scripts/validate_phase62b_sportmonks_wc_xg_lineups_completion.py
VAL_EXIT=$?

echo ""
echo "Output files:"
for f in \
  PHASE_62B_SPORTMONKS_WC_XG_LINEUPS_COMPLETION_REPORT.md \
  data/validation/phase62b_sportmonks_wc_completion.json \
  data/validation/phase62b_mapping_audit.json \
  data/validation/phase62b_progress.json \
  data/validation/phase62b_validation_summary.json
do
  if [[ -f "$f" ]]; then
    ls -lh "$f"
  else
    echo "  MISSING: $f"
  fi
done

ENRICHED_DIR="data/egie/world_cup/raw/goal_timing_features_enriched"
if [[ -d "$ENRICHED_DIR" ]]; then
  COUNT=$(find "$ENRICHED_DIR" -name '*.json' | wc -l | tr -d ' ')
  echo "Enriched feature rows: $COUNT"
fi

exit "$VAL_EXIT"
