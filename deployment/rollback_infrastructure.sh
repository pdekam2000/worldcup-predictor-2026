#!/usr/bin/env bash
# Rollback football-strength shadow infrastructure deploy.
# Restores previous application commit; leaves additive tables in place by default.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
PRE_COMMIT="${PRE_COMMIT:-}"
BACKUP_ROOT="${BACKUP_ROOT:-$APP/backups/infra_deploy}"
SERVICES="${SERVICES:-worldcup-api worldcup-gpt-actions}"
PYTHON="${PYTHON:-$APP/.venv/bin/python}"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
DROP_TABLES="${DROP_TABLES:-0}"

die() { echo "FATAL: $*" >&2; exit 1; }
step() { echo; echo "=== $* ==="; }

cd "$APP" || die "APP not found: $APP"

if [[ -z "$PRE_COMMIT" ]]; then
  # Try latest backup marker
  LATEST="$(ls -1dt "$BACKUP_ROOT"/* 2>/dev/null | head -n1 || true)"
  if [[ -n "$LATEST" && -f "$LATEST/pre_commit.txt" ]]; then
    PRE_COMMIT="$(tr -d '\r\n' <"$LATEST/pre_commit.txt")"
    echo "pre_commit_from_backup=$PRE_COMMIT ($LATEST)"
  fi
fi
[[ -n "$PRE_COMMIT" ]] || die "set PRE_COMMIT=<sha> or provide backup with pre_commit.txt"

step "1. record current (failed) commit"
CUR="$(git rev-parse HEAD)"
echo "current=$CUR"
echo "rollback_to=$PRE_COMMIT"

step "2. restore previous commit"
git fetch origin || true
git checkout --detach "$PRE_COMMIT"
[[ "$(git rev-parse HEAD)" == "$(git rev-parse "$PRE_COMMIT^{commit}")" ]] || die "checkout failed"

step "3. restart services"
# shellcheck disable=SC2086
sudo systemctl restart $SERVICES
sleep 3
# shellcheck disable=SC2086
for svc in $SERVICES; do
  systemctl is-active --quiet "$svc" || die "service not active: $svc"
done

step "4. health verify"
"$PYTHON" deployment/post_deploy_healthcheck.py \
  --api-base "$API_BASE" \
  --fi-db "${FI_DB:-$APP/data/football_intelligence.db}" \
  --out "/tmp/rollback_healthcheck.json" \
  || echo "WARN: healthcheck reported failures — investigate before declaring rollback complete"

step "5. additive tables"
if [[ "$DROP_TABLES" == "1" ]]; then
  echo "DROP_TABLES=1 — owner-approved destructive cleanup"
  sqlite3 "${FI_DB:-$APP/data/football_intelligence.db}" <<'SQL'
DROP TABLE IF EXISTS alternate_totals_capture_status;
DROP TABLE IF EXISTS totals_market_shadow_snapshots;
DROP TABLE IF EXISTS lambda_v2_shadow_outputs;
DROP TABLE IF EXISTS derived_historical_team_form_snapshots;
SQL
else
  echo "Leaving additive shadow tables in place (safe default)."
fi

step "6. summary"
cat <<EOF
status=ROLLBACK_COMPLETE
restored_commit=$(git rev-parse HEAD)
previous_bad_commit=$CUR
canonical_data=INTACT (no freeze restore required for additive infra)
tables_dropped=$DROP_TABLES
EOF
