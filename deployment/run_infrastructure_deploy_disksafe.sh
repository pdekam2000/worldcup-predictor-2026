#!/usr/bin/env bash
# Production Gate-0 infra deploy runner (disk-safe FI backup).
# Continues validated release package; does not promote models.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
RELEASE_REF="${RELEASE_REF:-origin/release/football-strength-shadow-infra-20260730T151432Z}"
RELEASE_BRANCH="${RELEASE_BRANCH:-release/football-strength-shadow-infra-20260730T151432Z}"
BACKUP_ROOT="${BACKUP_ROOT:-$APP/backups/infra_deploy}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${BACKUP_ROOT}/${TS}"
PYTHON="${PYTHON:-$APP/.venv/bin/python}"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
FI_DB="${FI_DB:-$APP/data/football_intelligence.db}"
SERVICES="${SERVICES:-worldcup-api worldcup-gpt-actions}"
FORCE_DIRTY="${FORCE_DIRTY:-1}"

die() { echo "FATAL: $*" >&2; exit 1; }
step() { echo; echo "=== $* ==="; }

cd "$APP" || die "APP not found: $APP"

step "0. preflight disk/services"
df -h / | tee "$RUN_DIR/../_preflight_df.txt" >/dev/null || true
mkdir -p "$RUN_DIR/db" "$RUN_DIR/env"
df -h / | tee "$RUN_DIR/df_before.txt"
systemctl is-active worldcup-api worldcup-gpt-actions nginx | tee "$RUN_DIR/services_before.txt"

step "1. verify git status"
git rev-parse --is-inside-work-tree >/dev/null || die "not a git repo"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "WARN: dirty tracked files present"
  [[ "$FORCE_DIRTY" == "1" ]] || die "working tree dirty; set FORCE_DIRTY=1"
fi

step "2. record current commit"
PRE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
PRE_COMMIT="$(git rev-parse HEAD)"
echo "pre_branch=$PRE_BRANCH"
echo "pre_commit=$PRE_COMMIT"
printf '%s\n' "$PRE_BRANCH" >"$RUN_DIR/pre_branch.txt"
printf '%s\n' "$PRE_COMMIT" >"$RUN_DIR/pre_commit.txt"

step "3. fetch release"
git fetch origin "$RELEASE_BRANCH"
TARGET="$(git rev-parse "${RELEASE_REF}^{commit}")"
echo "deploy_target=$TARGET"
printf '%s\n' "$TARGET" >"$RUN_DIR/resolved_target.txt"

step "4. backup env + eval DB + FI fingerprint/compressed"
cp -a "$APP/.env.production" "$RUN_DIR/env/.env.production"
wc -c <"$APP/.env.production" >"$RUN_DIR/env/env_bytes.txt"
if [[ -f "$APP/data/evaluation/forward_prediction_tracking.db" ]]; then
  mkdir -p "$RUN_DIR/db/evaluation"
  cp -a "$APP/data/evaluation/forward_prediction_tracking.db" "$RUN_DIR/db/evaluation/"
fi
[[ -f "$FI_DB" ]] || die "FI DB missing: $FI_DB"
sha256sum "$FI_DB" | tee "$RUN_DIR/db/football_intelligence.sha256"
# Raw 11G copy will not fit (~12G free). Compressed backup + SHA256 for additive DDL.
if command -v pigz >/dev/null 2>&1; then
  nice pigz -1 -c "$FI_DB" >"$RUN_DIR/db/football_intelligence.db.gz"
else
  nice gzip -1 -c "$FI_DB" >"$RUN_DIR/db/football_intelligence.db.gz"
fi
ls -lh "$RUN_DIR/db/football_intelligence.db.gz" | tee "$RUN_DIR/db/fi_gz_ls.txt"
df -h / | tee "$RUN_DIR/df_after_backup.txt"

step "5. checkout release commit"
git checkout --detach "$TARGET"
POST_COMMIT="$(git rev-parse HEAD)"
echo "post_commit=$POST_COMMIT"
[[ "$POST_COMMIT" == "$TARGET" ]] || die "checkout mismatch"

step "6. verify migrations additive-only"
for f in \
  migrations/research_football_strength_lambda_v2.sql \
  migrations/research_alternate_totals_capture_status.sql
do
  [[ -f "$f" ]] || die "missing migration: $f"
  if grep -Ev '^[[:space:]]*--' "$f" | grep -Eiq 'drop[[:space:]]+table|alter[[:space:]]+table.*(drop|rename)|delete[[:space:]]+from[[:space:]]+frozen|update[[:space:]]+frozen'; then
    die "unsafe DDL detected in $f"
  fi
  grep -Eq 'CREATE TABLE IF NOT EXISTS' "$f" || die "expected CREATE TABLE IF NOT EXISTS in $f"
done
echo "migrations_verified=ok"

step "7. apply additive migrations"
"$PYTHON" - <<PY
import sqlite3, pathlib
db = pathlib.Path(r"""$FI_DB""")
conn = sqlite3.connect(db)
for rel in (
    "migrations/research_football_strength_lambda_v2.sql",
    "migrations/research_alternate_totals_capture_status.sql",
):
    conn.executescript(pathlib.Path(rel).read_text(encoding="utf-8"))
need = {
    "derived_historical_team_form_snapshots",
    "totals_market_shadow_snapshots",
    "lambda_v2_shadow_outputs",
    "alternate_totals_capture_status",
}
have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
missing = sorted(need - have)
if missing:
    raise SystemExit(f"missing tables after migrate: {missing}")
conn.close()
print("migrations_applied=ok")
PY

step "8. restart services"
# shellcheck disable=SC2086
sudo systemctl restart $SERVICES
sleep 4
# shellcheck disable=SC2086
for svc in $SERVICES; do
  systemctl is-active --quiet "$svc" || die "service not active: $svc"
done
systemctl is-active --quiet nginx && echo "nginx=active" || echo "WARN: nginx not active"

step "9. health checks"
"$PYTHON" deployment/post_deploy_healthcheck.py \
  --api-base "$API_BASE" \
  --fi-db "$FI_DB" \
  --out "$RUN_DIR/post_deploy_healthcheck.json" \
  || die "healthcheck failed"

step "10. canonical regression probe"
"$PYTHON" deployment/canonical_regression_probe.py \
  --mode after \
  --baseline-dir "$RUN_DIR" \
  --fi-db "$FI_DB" \
  --out-md "$RUN_DIR/canonical_regression_report.md" \
  --out-json "$RUN_DIR/canonical_regression.json" \
  || die "canonical regression failed"

step "11. shadow probe"
"$PYTHON" deployment/shadow_probe.py \
  --fi-db "$FI_DB" \
  --out-md "$RUN_DIR/shadow_probe_report.md" \
  --out-json "$RUN_DIR/shadow_probe.json" \
  || die "shadow probe failed"

step "12. log secret scan"
# shellcheck disable=SC2086
for svc in $SERVICES; do
  journalctl -u "$svc" -n 80 --no-pager >"$RUN_DIR/journal_${svc}.log" || true
done
if grep -Eiq 'api[_-]?key|jwt_secret|password=|bearer [a-z0-9]{20,}' "$RUN_DIR"/journal_*.log 2>/dev/null; then
  die "possible secret material in recent journal output"
fi
echo "log_secret_scan=ok"

step "13. summary"
cat >"$RUN_DIR/DEPLOYMENT_SUMMARY.txt" <<EOF
status=SUCCESS
timestamp_utc=$TS
app=$APP
pre_commit=$PRE_COMMIT
post_commit=$POST_COMMIT
release_branch=$RELEASE_BRANCH
validated_infra=537266d
package_tip_ref=$TARGET
migrations=research_football_strength_lambda_v2.sql,research_alternate_totals_capture_status.sql
services_restarted=$SERVICES
backup_dir=$RUN_DIR
fi_backup=compressed_gz_plus_sha256
canonical_promotion=NONE
lambda_v2_canonical=NO
exact_v2_canonical=NO
EOF
cat "$RUN_DIR/DEPLOYMENT_SUMMARY.txt"
echo "Artifacts: $RUN_DIR"
echo "Rollback: PRE_COMMIT=$PRE_COMMIT bash deployment/rollback_infrastructure.sh"
