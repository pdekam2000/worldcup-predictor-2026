#!/bin/bash
# Phase 54H-4 controlled server pressure backfill batch 1
set -eu
cd /opt/worldcup-predictor
PY="${PY:-.venv/bin/python3}"
if [ ! -x "$PY" ]; then PY=python3; fi
set -a
# shellcheck disable=SC1091
source .env.production
set +a

ART=artifacts/phase54h4_pressure_backfill_batch1
mkdir -p "$ART" data/feature_store/sportmonks_pressure/raw

echo "=== PRERUN ==="
$PY scripts/validate_phase54h4_pressure_backfill_prerun.py | tee "$ART/prerun.log"
PRERUN=${PIPESTATUS[0]}
if [ "$PRERUN" -ne 0 ]; then
  echo "PRERUN_FAILED exit=$PRERUN"
  exit 1
fi

BEFORE=$($PY -c "import json;print(json.load(open('$ART/prerun_validation.json')).get('pre_run_fixture_count',0))")
echo "FIXTURES_BEFORE=$BEFORE"

echo "=== TARGET MANIFEST ==="
$PY scripts/build_phase54h4_target_fixtures.py | tee "$ART/target_build.log"

run_batch() {
  local LEAGUE=$1
  local JOB=$2
  echo "=== BATCH $JOB league=$LEAGUE ==="
  $PY scripts/phase54h_pressure_feature_store_backfill.py \
    --league-id "$LEAGUE" \
    --max-calls 30 \
    --cache-first \
    --skip-existing \
    --save-raw \
    --job-key "$JOB" \
    --artifact-dir "$ART" \
    --max-pages 10 2>&1 | tee "$ART/${JOB}.log"
  local EC=${PIPESTATUS[0]}
  if [ "$EC" -ne 0 ]; then
    echo "BATCH_FAILED $JOB exit=$EC"
    return "$EC"
  fi
  EMPTY=$($PY -c "import json;d=json.load(open('$ART/backfill_${JOB}.json',errors='ignore') or open('$ART/backfill_result.json'));b=d.get('backfill',{});print(int(b.get('fixtures_empty',0))+int(b.get('fixtures_error',0)))" 2>/dev/null || echo 0)
  PROC=$($PY -c "import json;d=json.load(open('$ART/backfill_${JOB}.json',errors='ignore') or open('$ART/backfill_result.json'));print(int(d.get('backfill',{}).get('fixtures_processed',0)))" 2>/dev/null || echo 0)
  if [ "$PROC" -gt 0 ] && [ "$EMPTY" -eq "$PROC" ]; then
    echo "BATCH_ALL_EMPTY $JOB — stopping early"
    return 2
  fi
  return 0
}

run_batch 732 phase54h4_wc_batch1 || true
run_batch 2 phase54h4_cl_batch1 || true
run_batch 5 phase54h4_el_batch1 || true

AFTER_PARTIAL=$($PY -c "from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository as R;import json;a=R().audit_coverage();print(int((a.get('records') or {}).get('fixture_count') or 0))")
echo "FIXTURES_AFTER_PARTIAL=$AFTER_PARTIAL"

if [ "$AFTER_PARTIAL" -lt 150 ]; then
  run_batch 2286 phase54h4_conference_batch1 || true
fi

echo "=== COVERAGE AUDIT ==="
$PY scripts/audit_phase54h4_pressure_backfill_coverage.py | tee "$ART/audit.log"

echo "=== VALIDATION ==="
$PY scripts/validate_phase54h4_pressure_backfill_batch1.py | tee "$ART/validation.log"
