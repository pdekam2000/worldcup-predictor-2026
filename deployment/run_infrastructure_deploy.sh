#!/usr/bin/env bash
# Controlled infrastructure-only deploy for football-strength shadow infra.
# Target commit: 537266d (release/football-strength-shadow-infra-20260730T151432Z)
# Does NOT promote Lambda V2 / Exact V2 / adaptive selector to canonical.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
RELEASE_REF="${RELEASE_REF:-c8e68d7}"
RELEASE_BRANCH="${RELEASE_BRANCH:-release/football-strength-shadow-infra-20260730T151432Z}"
# Infra-validated SHA (included in ancestry): 537266d
BACKUP_ROOT="${BACKUP_ROOT:-$APP/backups/infra_deploy}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${BACKUP_ROOT}/${TS}"
PYTHON="${PYTHON:-$APP/.venv/bin/python}"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
FI_DB="${FI_DB:-$APP/data/football_intelligence.db}"
SERVICES="${SERVICES:-worldcup-api worldcup-gpt-actions}"

die() { echo "FATAL: $*" >&2; exit 1; }
step() { echo; echo "=== $* ==="; }

cd "$APP" || die "APP not found: $APP"

step "1. verify git status"
git rev-parse --is-inside-work-tree >/dev/null || die "not a git repo"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "WARN: dirty tracked files present; continuing only if FORCE_DIRTY=1"
  [[ "${FORCE_DIRTY:-0}" == "1" ]] || die "working tree has tracked modifications; set FORCE_DIRTY=1 to override"
fi

step "2. verify / record current branch + commit"
PRE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
PRE_COMMIT="$(git rev-parse HEAD)"
echo "pre_branch=$PRE_BRANCH"
echo "pre_commit=$PRE_COMMIT"
mkdir -p "$RUN_DIR"
printf '%s\n' "$PRE_BRANCH" >"$RUN_DIR/pre_branch.txt"
printf '%s\n' "$PRE_COMMIT" >"$RUN_DIR/pre_commit.txt"
printf '%s\n' "$RELEASE_REF" >"$RUN_DIR/target_commit.txt"

step "3. fetch release"
git fetch origin "$RELEASE_BRANCH" || git fetch origin
if git cat-file -e "${RELEASE_REF}^{commit}" 2>/dev/null; then
  TARGET="$(git rev-parse "${RELEASE_REF}^{commit}")"
elif git cat-file -e "origin/${RELEASE_BRANCH}^{commit}" 2>/dev/null; then
  TARGET="$(git rev-parse "origin/${RELEASE_BRANCH}^{commit}")"
else
  die "cannot resolve RELEASE_REF=$RELEASE_REF or origin/$RELEASE_BRANCH"
fi
echo "deploy_target=$TARGET"
printf '%s\n' "$TARGET" >"$RUN_DIR/resolved_target.txt"

step "4. backup database (sqlite FI + optional eval)"
mkdir -p "$RUN_DIR/db"
if [[ -f "$FI_DB" ]]; then
  cp -a "$FI_DB" "$RUN_DIR/db/football_intelligence.db"
  echo "backed_up=$FI_DB"
else
  echo "WARN: FI DB missing at $FI_DB"
fi
if [[ -f "$APP/data/evaluation/forward_prediction_tracking.db" ]]; then
  mkdir -p "$RUN_DIR/db/evaluation"
  cp -a "$APP/data/evaluation/forward_prediction_tracking.db" "$RUN_DIR/db/evaluation/"
fi
if command -v pg_dump >/dev/null 2>&1 && [[ -n "${DATABASE_URL:-}" ]]; then
  pg_dump -Fc "$DATABASE_URL" >"$RUN_DIR/db/postgres.dump" || echo "WARN: pg_dump failed (non-fatal if sqlite-only path)"
fi

step "5. backup environment (no secret echo)"
mkdir -p "$RUN_DIR/env"
if [[ -f "$APP/.env.production" ]]; then
  cp -a "$APP/.env.production" "$RUN_DIR/env/.env.production"
  wc -c <"$APP/.env.production" >"$RUN_DIR/env/env_bytes.txt"
  echo "env_backed_up=yes"
else
  die ".env.production missing"
fi

step "6. checkout release commit"
git checkout --detach "$TARGET"
POST_COMMIT="$(git rev-parse HEAD)"
echo "post_commit=$POST_COMMIT"
[[ "$POST_COMMIT" == "$TARGET" ]] || die "checkout mismatch"

step "7. verify migrations present + additive-only"
for f in \
  migrations/research_football_strength_lambda_v2.sql \
  migrations/research_alternate_totals_capture_status.sql
do
  [[ -f "$f" ]] || die "missing migration: $f"
  if grep -Eiq 'drop table|alter table.*(drop|rename)|delete from frozen|update frozen' "$f"; then
    die "unsafe DDL detected in $f"
  fi
  grep -Eq 'CREATE TABLE IF NOT EXISTS' "$f" || die "expected CREATE TABLE IF NOT EXISTS in $f"
done
echo "migrations_verified=ok"

step "8. apply additive migrations to FI sqlite"
[[ -f "$FI_DB" ]] || die "cannot apply migrations; FI DB missing"
"$PYTHON" - <<PY
import sqlite3, pathlib
db = pathlib.Path(r"""$FI_DB""")
conn = sqlite3.connect(db)
for rel in (
    "migrations/research_football_strength_lambda_v2.sql",
    "migrations/research_alternate_totals_capture_status.sql",
):
    sql = pathlib.Path(rel).read_text(encoding="utf-8")
    conn.executescript(sql)
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

step "9. restart required services"
# shellcheck disable=SC2086
sudo systemctl restart $SERVICES
sleep 3
# shellcheck disable=SC2086
for svc in $SERVICES; do
  systemctl is-active --quiet "$svc" || die "service not active: $svc"
done
systemctl is-active --quiet nginx && echo "nginx=active" || echo "WARN: nginx not active"

step "10. health checks"
"$PYTHON" deployment/post_deploy_healthcheck.py \
  --api-base "$API_BASE" \
  --fi-db "$FI_DB" \
  --out "$RUN_DIR/post_deploy_healthcheck.json" \
  || die "healthcheck failed"

step "11. canonical regression probe"
"$PYTHON" deployment/canonical_regression_probe.py \
  --mode after \
  --baseline-dir "$RUN_DIR" \
  --fi-db "$FI_DB" \
  --out-md "$RUN_DIR/canonical_regression_report.md" \
  --out-json "$RUN_DIR/canonical_regression.json" \
  || die "canonical regression failed"

step "12-15. shadow probe + persistence"
"$PYTHON" deployment/shadow_probe.py \
  --fi-db "$FI_DB" \
  --out-md "$RUN_DIR/shadow_probe_report.md" \
  --out-json "$RUN_DIR/shadow_probe.json" \
  || die "shadow probe failed"

step "16. verify logs (no obvious secrets)"
# shellcheck disable=SC2086
for svc in $SERVICES; do
  sudo journalctl -u "$svc" -n 80 --no-pager >"$RUN_DIR/journal_${svc}.log" || true
done
if grep -Eiq 'api[_-]?key|jwt_secret|password=|bearer [a-z0-9]{20,}' "$RUN_DIR"/journal_*.log 2>/dev/null; then
  die "possible secret material in recent journal output"
fi
echo "log_secret_scan=ok"

step "17. deployment summary"
cat >"$RUN_DIR/DEPLOYMENT_SUMMARY.txt" <<EOF
status=SUCCESS
timestamp_utc=$TS
app=$APP
pre_commit=$PRE_COMMIT
post_commit=$POST_COMMIT
release_branch=$RELEASE_BRANCH
validated_target=537266d
package_commit=c8e68d7
migrations=research_football_strength_lambda_v2.sql,research_alternate_totals_capture_status.sql
services_restarted=$SERVICES
backup_dir=$RUN_DIR
canonical_promotion=NONE
lambda_v2_canonical=NO
exact_v2_canonical=NO
EOF
cat "$RUN_DIR/DEPLOYMENT_SUMMARY.txt"
echo
echo "Artifacts: $RUN_DIR"
echo "Rollback: APP=$APP PRE_COMMIT=$PRE_COMMIT bash deployment/rollback_infrastructure.sh"
