#!/bin/bash
# Phase 54H-5 controlled server pressure expansion to 150+ fixtures
set -eu
cd /opt/worldcup-predictor
PY="${PY:-.venv/bin/python3}"
if [ ! -x "$PY" ]; then PY=python3; fi
set -a
# shellcheck disable=SC1091
source .env.production
set +a

ART=artifacts/phase54h5_pressure_expansion
mkdir -p "$ART" data/feature_store/sportmonks_pressure/raw data/egie/uefa_club/raw

echo "=== PART A — SERVER STATE ==="
$PY scripts/check_phase54h5_server_state.py | tee "$ART/state_check.log"
BEFORE=$($PY -c "import json;print(json.load(open('$ART/pre_run_state.json')).get('pressure_fixture_count',0))")
echo "FIXTURES_BEFORE=$BEFORE"

run_wc_batch() {
  local JOB=$1
  local COUNT
  COUNT=$($PY -c "from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository as R;print(int((R().audit_coverage().get('records') or {}).get('fixture_count') or 0))")
  if [ "$COUNT" -ge 150 ]; then
    echo "SKIP $JOB — already at $COUNT fixtures"
    return 0
  fi
  echo "=== WC BATCH $JOB (fixtures=$COUNT) ==="
  $PY scripts/phase54h_pressure_feature_store_backfill.py \
    --league-id 732 \
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
  EMPTY=$($PY -c "import json;d=json.load(open('$ART/backfill_${JOB}.json'));b=d.get('backfill',{});print(int(b.get('fixtures_empty',0)))" 2>/dev/null || echo 0)
  PROC=$($PY -c "import json;d=json.load(open('$ART/backfill_${JOB}.json'));b=d.get('backfill',{});print(int(b.get('fixtures_processed',0)))" 2>/dev/null || echo 0)
  IMP=$($PY -c "import json;d=json.load(open('$ART/backfill_${JOB}.json'));b=d.get('backfill',{});print(int(b.get('fixtures_imported',0)))" 2>/dev/null || echo 0)
  if [ "$PROC" -gt 0 ] && [ "$EMPTY" -eq "$PROC" ]; then
    echo "BATCH_ALL_EMPTY $JOB — stopping WC batches"
    return 2
  fi
  if [ "$IMP" -eq 0 ] && [ "$PROC" -eq 0 ]; then
    echo "BATCH_NO_WORK $JOB"
    return 2
  fi
  return 0
}

echo "=== PART B — WC BATCHES ==="
run_wc_batch phase54h5_wc_batch2 || true
run_wc_batch phase54h5_wc_batch3 || true
run_wc_batch phase54h5_wc_batch4 || true

echo "=== PART C — UEFA PRIOR-SEASON DISCOVERY ==="
$PY scripts/discover_phase54h5_uefa_prior_seasons.py | tee "$ART/uefa_discovery.log"

AFTER_WC=$($PY -c "from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository as R;print(int((R().audit_coverage().get('records') or {}).get('fixture_count') or 0))")
echo "FIXTURES_AFTER_WC=$AFTER_WC"

echo "=== PART D — CACHE SEED (if <150) ==="
if [ "$AFTER_WC" -lt 150 ]; then
  if [ -d data/egie/uefa_club/raw ] && [ "$(find data/egie/uefa_club/raw -maxdepth 1 -name '*.json' | wc -l)" -gt 0 ]; then
    $PY scripts/seed_phase54h5_pressure_cache.py | tee "$ART/cache_seed.log"
  else
    echo '{"status":"skipped","reason":"no_uefa_cache_on_server"}' > "$ART/cache_seed_result.json"
    echo "CACHE_SEED_SKIPPED no files"
  fi
else
  echo '{"status":"skipped","reason":"target_already_met"}' > "$ART/cache_seed_result.json"
  echo "CACHE_SEED_SKIPPED target met"
fi

echo "=== PART E — COVERAGE AUDIT ==="
$PY scripts/audit_phase54h5_pressure_coverage.py | tee "$ART/audit.log"

echo "=== PART F — VALIDATION ==="
$PY scripts/validate_phase54h5_pressure_backfill_expansion.py | tee "$ART/validation.log"
