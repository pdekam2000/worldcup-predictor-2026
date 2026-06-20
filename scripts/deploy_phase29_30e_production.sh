#!/usr/bin/env bash
# Production deploy: Phase 29 + 30A + 30C + 30E
set -euo pipefail

APP=/opt/worldcup-predictor
WEB=/var/www/worldcup/frontend/dist
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$APP/backups/deploy-phase29-30e-$TS"
IP="${DEPLOY_IP:-91.107.188.229}"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; exit 1; }
info() { printf 'INFO\t%s\n' "$1"; }

rollback() {
  info "ROLLBACK triggered"
  if [[ -f "$BACKUP_DIR/pre_deploy_commit.txt" ]]; then
    ROLLBACK_COMMIT=$(cat "$BACKUP_DIR/pre_deploy_commit.txt")
    cd "$APP"
    git checkout "$ROLLBACK_COMMIT"
    systemctl restart worldcup-api || true
    if [[ -d "$BACKUP_DIR/frontend_dist" ]]; then
      rm -rf "$WEB"
      cp -a "$BACKUP_DIR/frontend_dist" "$WEB"
    fi
    info "Rolled back to $ROLLBACK_COMMIT"
  fi
  exit 1
}

trap 'rollback' ERR

info "=== Step 0: Pre-deploy state ==="
cd "$APP"
git status --short || true
PRE_COMMIT=$(git rev-parse HEAD)
git log -1 --oneline

info "=== Step 1: Full backup ==="
mkdir -p "$BACKUP_DIR"
echo "$PRE_COMMIT" > "$BACKUP_DIR/pre_deploy_commit.txt"
tar czf "$BACKUP_DIR/repo_snapshot.tar.gz" \
  --exclude=.git \
  --exclude=node_modules \
  --exclude=base44-d/node_modules \
  --exclude=.venv \
  --exclude="./backups/deploy-phase29-30e-$TS" \
  .
if [[ -d "$WEB" ]]; then
  cp -a "$WEB" "$BACKUP_DIR/frontend_dist"
  pass "Frontend dist backed up"
fi
pass "Backup directory: $BACKUP_DIR ($(du -sh "$BACKUP_DIR" | awk '{print $1}'))"

info "=== Step 2: Git pull ==="
git fetch origin main
git checkout main
git pull origin main
NEW_COMMIT=$(git rev-parse HEAD)
git log -1 --oneline
echo "$NEW_COMMIT" > "$BACKUP_DIR/post_deploy_commit.txt"

info "=== Step 3: Permissions (www-data cache/data) ==="
mkdir -p "$APP/data" "$APP/.cache/api_football" "$APP/logs" "$APP/backups" \
  "$APP/data/shadow" "$APP/data/validation"
chown -R www-data:www-data "$APP/data" "$APP/.cache" "$APP/logs" "$APP/backups" \
  "$APP/data/shadow" "$APP/data/validation" 2>/dev/null || true
chmod -R u+rwX,g+rwX "$APP/data" "$APP/.cache" 2>/dev/null || true
pass "Permissions set for www-data"

info "=== Step 4: Backend validation ==="
cd "$APP"
.venv/bin/python scripts/validate_phase29_prediction_history_results.py
.venv/bin/python scripts/validate_phase30a_prediction_output_completeness.py
.venv/bin/python scripts/validate_phase30c_market_ranking_engine.py
.venv/bin/python scripts/validate_phase30e_data_coverage_repair.py
pass "All validation scripts passed"

info "=== Step 5: Restart FastAPI ==="
systemctl restart worldcup-api
sleep 5
if systemctl is-active --quiet worldcup-api; then
  pass "worldcup-api active"
else
  fail "worldcup-api failed to start"
fi

info "=== Step 6: Backend health ==="
curl -sf http://127.0.0.1:8000/api/health | head -c 500
echo
pass "Local /api/health OK"

info "=== Step 7: Predict smoke (1539007) ==="
curl -sf -X POST "http://127.0.0.1:8000/api/predict/1539007" -o /tmp/pred_30e.json
"$APP/.venv/bin/python" <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/pred_30e.json").read_text())
checks = [
    ("status_ok", d.get("status") == "ok"),
    ("recommended_bets", "recommended_bets" in d),
    ("detailed_markets", "detailed_markets" in d),
    ("market_ranking", "market_ranking" in d),
    ("safe_pick_key", "safe_pick" in d),
    ("ou_in_probabilities", "over_under_2_5" in (d.get("probabilities") or {})),
    ("btts_in_probabilities", "btts" in (d.get("probabilities") or {})),
]
sig = d.get("data_signals") or {}
checks += [
    ("missing_lineups_false", sig.get("missing_lineups") is False),
    ("odds_available_true", sig.get("odds_available") is True),
    ("official_lineup_pending", sig.get("official_lineup_pending") is True),
]
for name, ok in checks:
    print("PASS" if ok else "FAIL", name, sig if name.startswith("missing") or name.startswith("odds") or name.startswith("official") else "")
if not all(c[1] for c in checks):
    raise SystemExit(1)
PY
pass "Predict 1539007 Phase 30E signals OK"

info "=== Step 8: Frontend build ==="
cd "$APP/base44-d"
if [[ ! -f .env.production ]]; then
  printf '%s\n' 'VITE_API_BASE_URL=' > .env.production
fi
npm ci
npm run build
pass "Frontend build OK"

info "=== Step 9: Deploy frontend ==="
FRONT_BACKUP="/var/www/worldcup/frontend/dist-backup-phase30e-$TS"
if [[ -d "$WEB" ]]; then
  cp -a "$WEB" "$FRONT_BACKUP"
  info "Frontend rollback backup: $FRONT_BACKUP"
fi
mkdir -p "$WEB"
rsync -a --delete dist/ "$WEB/"
chown -R www-data:www-data "$WEB"
pass "Frontend deployed to $WEB"

info "=== Step 10: Public checks ==="
curl -sf "http://127.0.0.1/api/health" >/dev/null && pass "nginx /api/health" || fail "nginx /api/health"
curl -sf "http://$IP/api/health" >/dev/null && pass "public /api/health" || fail "public /api/health"

trap - ERR
info "=== Deploy complete ==="
echo "PRE_COMMIT=$PRE_COMMIT"
echo "NEW_COMMIT=$NEW_COMMIT"
echo "BACKUP_DIR=$BACKUP_DIR"
echo "ROLLBACK_CMD=cd $APP && git checkout $PRE_COMMIT && systemctl restart worldcup-api && rm -rf $WEB && cp -a $BACKUP_DIR/frontend_dist $WEB"
