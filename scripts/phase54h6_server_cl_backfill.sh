#!/bin/bash
# Phase 54H-6 UEFA CL prior-season pressure backfill to 150+ threshold
set -eu
cd /opt/worldcup-predictor
PY="${PY:-.venv/bin/python3}"
if [ ! -x "$PY" ]; then PY=python3; fi
set -a
# shellcheck disable=SC1091
source .env.production
set +a

ART=artifacts/phase54h6_pressure_threshold
mkdir -p "$ART" data/feature_store/sportmonks_pressure/raw

echo "=== PART A — PRE-RUN ==="
$PY scripts/check_phase54h6_pre_run.py | tee "$ART/pre_run.log"
BEFORE=$($PY -c "import json;print(json.load(open('$ART/pre_run_state.json')).get('pressure_fixture_count',0))")
GAP=$($PY -c "import json;print(json.load(open('$ART/pre_run_state.json')).get('gap_to_target',0))")
echo "FIXTURES_BEFORE=$BEFORE GAP=$GAP"

if [ "$BEFORE" -ge 150 ]; then
  echo "THRESHOLD_ALREADY_MET"
  $PY scripts/audit_phase54h6_pressure_coverage.py | tee "$ART/audit.log"
  $PY scripts/validate_phase54h6_pressure_threshold.py | tee "$ART/validation.log"
  exit 0
fi

echo "=== PART B — CL 2024/25 BACKFILL ==="
$PY scripts/phase54h_pressure_feature_store_backfill.py \
  --league-id 2 \
  --season-id 23619 \
  --max-calls 40 \
  --cache-first \
  --skip-existing \
  --save-raw \
  --job-key phase54h6_cl_priorseason \
  --artifact-dir "$ART" \
  --max-pages 15 2>&1 | tee "$ART/phase54h6_cl_priorseason.log"

BF="$ART/backfill_phase54h6_cl_priorseason.json"
EMPTY=$($PY -c "import json;d=json.load(open('$BF'));b=d.get('backfill',{});print(int(b.get('fixtures_empty',0)))" 2>/dev/null || echo 0)
ERR=$($PY -c "import json;d=json.load(open('$BF'));b=d.get('backfill',{});print(int(b.get('fixtures_error',0)))" 2>/dev/null || echo 0)
PROC=$($PY -c "import json;d=json.load(open('$BF'));b=d.get('backfill',{});print(int(b.get('fixtures_processed',0)))" 2>/dev/null || echo 0)
if [ "$PROC" -gt 0 ] && [ "$EMPTY" -eq "$PROC" ]; then
  echo "STOP_ALL_EMPTY"
  exit 2
fi
if [ "$ERR" -gt 5 ]; then
  echo "STOP_HIGH_ERROR_RATE"
  exit 3
fi

echo "=== PART C/D — COVERAGE AUDIT + THRESHOLD ==="
$PY scripts/audit_phase54h6_pressure_coverage.py | tee "$ART/audit.log"

echo "=== PART E — VALIDATION ==="
$PY scripts/validate_phase54h6_pressure_threshold.py | tee "$ART/validation.log"
