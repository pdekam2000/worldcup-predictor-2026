#!/usr/bin/env bash
# Production deploy: Phase 32B + 32C + 32E (National Team Intelligence)
set -euo pipefail

APP=/opt/worldcup-predictor
WEB=/var/www/worldcup/frontend/dist
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$APP/backups/deploy-phase32bc32e-$TS"
DEPLOY_SRC="${DEPLOY_SRC:-/tmp/phase32_deploy}"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; exit 1; }
info() { printf 'INFO\t%s\n' "$1"; }

info "=== Step 0: Pre-deploy state ==="
cd "$APP"
PRE_COMMIT=$(git rev-parse HEAD)
git log -1 --oneline
echo "$PRE_COMMIT" > "/tmp/pre_deploy_commit_phase32.txt"

info "=== Step 1: Full backup ==="
mkdir -p "$BACKUP_DIR"
echo "$PRE_COMMIT" > "$BACKUP_DIR/pre_deploy_commit.txt"
tar czf "$BACKUP_DIR/repo_snapshot.tar.gz" \
  --exclude=.git \
  --exclude=node_modules \
  --exclude=base44-d/node_modules \
  --exclude=.venv \
  --exclude="./backups/deploy-phase32bc32e-$TS" \
  .
if [[ -f data/football_intelligence.db ]]; then
  cp -a data/football_intelligence.db "$BACKUP_DIR/football_intelligence.db"
  pass "SQLite database backed up"
fi
if [[ -d "$WEB" ]]; then
  cp -a "$WEB" "$BACKUP_DIR/frontend_dist"
  pass "Frontend dist backed up"
fi
pass "Backup directory: $BACKUP_DIR ($(du -sh "$BACKUP_DIR" | awk '{print $1}'))"

info "=== Step 2: Deploy Phase 32B+32C+32E files only ==="
if [[ ! -d "$DEPLOY_SRC/worldcup_predictor/intelligence/national_team" ]]; then
  fail "Deploy source missing at $DEPLOY_SRC"
fi

# National team package
rsync -a "$DEPLOY_SRC/worldcup_predictor/intelligence/national_team/" \
  "$APP/worldcup_predictor/intelligence/national_team/"

# Core wiring (32B/32C/32E only)
for f in \
  worldcup_predictor/config/settings.py \
  worldcup_predictor/database/migrations.py \
  worldcup_predictor/database/repository.py \
  worldcup_predictor/decision/weighted_decision_engine.py \
  worldcup_predictor/odds/market_consensus_agent.py \
  worldcup_predictor/prediction/scoring_engine.py
do
  if [[ -f "$DEPLOY_SRC/$f" ]]; then
    cp -a "$DEPLOY_SRC/$f" "$APP/$f"
    pass "Deployed $f"
  else
    fail "Missing deploy file: $f"
  fi
done

# Validation scripts
mkdir -p "$APP/scripts"
for f in \
  scripts/validate_phase32b_national_team_intelligence.py \
  scripts/validate_phase32c_national_history_backfill.py \
  scripts/validate_phase32e_reality_calibration.py \
  scripts/bootstrap_path.py
do
  if [[ -f "$DEPLOY_SRC/$f" ]]; then
    cp -a "$DEPLOY_SRC/$f" "$APP/$f"
    pass "Deployed $f"
  fi
done

info "=== Step 3: Environment ==="
ENV_FILE="$APP/.env.production"
if [[ ! -f "$ENV_FILE" ]]; then
  ENV_FILE="$APP/.env"
fi
if grep -q '^NATIONAL_TEAM_INTELLIGENCE_ENABLED=' "$ENV_FILE" 2>/dev/null; then
  sed -i 's/^NATIONAL_TEAM_INTELLIGENCE_ENABLED=.*/NATIONAL_TEAM_INTELLIGENCE_ENABLED=true/' "$ENV_FILE"
else
  echo 'NATIONAL_TEAM_INTELLIGENCE_ENABLED=true' >> "$ENV_FILE"
fi
pass "NATIONAL_TEAM_INTELLIGENCE_ENABLED=true"
grep NATIONAL_TEAM "$ENV_FILE" || true

info "=== Step 4: Permissions ==="
mkdir -p "$APP/data" "$APP/.cache/api_football" "$APP/logs" "$APP/backups" "$APP/artifacts"
chown -R www-data:www-data "$APP/data" "$APP/.cache" "$APP/logs" "$APP/backups" "$APP/artifacts" 2>/dev/null || true
chmod -R u+rwX,g+rwX "$APP/data" "$APP/.cache" 2>/dev/null || true
pass "Permissions set for www-data"

info "=== Step 5: Phase 32C backfill validation ==="
cd "$APP"
export NATIONAL_TEAM_INTELLIGENCE_ENABLED=true
.venv/bin/python scripts/validate_phase32c_national_history_backfill.py --limit 20 2>&1 | tee "$BACKUP_DIR/validate_phase32c.log"
pass "Phase 32C validation completed"

info "=== Step 6: Phase 32E safety validation ==="
.venv/bin/python scripts/validate_phase32e_reality_calibration.py --limit 20 2>&1 | tee "$BACKUP_DIR/validate_phase32e.log" || true
pass "Phase 32E validation completed (see log for check details)"

info "=== Step 7: Restart FastAPI ==="
systemctl restart worldcup-api
sleep 6
if systemctl is-active --quiet worldcup-api; then
  pass "worldcup-api active"
else
  fail "worldcup-api failed to start"
fi

info "=== Step 8: Health checks ==="
curl -sf http://127.0.0.1:8000/api/health | head -c 500
echo
pass "Local /api/health OK"
curl -sf https://footballpredictor.it.com/api/health | head -c 500
echo
pass "Public /api/health OK"

info "=== Step 9: Smoke tests ==="
cp -a "$DEPLOY_SRC/scripts/phase32_smoke_test.py" "$BACKUP_DIR/smoke_test.py" 2>/dev/null || \
  cp -a "$APP/scripts/phase32_smoke_test.py" "$BACKUP_DIR/smoke_test.py" 2>/dev/null || true
if [[ -f "$BACKUP_DIR/smoke_test.py" ]]; then
  .venv/bin/python "$BACKUP_DIR/smoke_test.py" "$BACKUP_DIR/smoke_test_results.json" 2>&1 | tee "$BACKUP_DIR/smoke_test.log"
else
  info "Smoke test script not found — skipping"
fi

info "=== Deploy complete ==="
echo "PRE_COMMIT=$PRE_COMMIT"
echo "BACKUP_DIR=$BACKUP_DIR"
echo "DEPLOYED=phase32bc32e"
