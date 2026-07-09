#!/usr/bin/env bash
# Phase 2 — safe production deploy (ff-only, backup gate, validation, controlled restart).
# Composes patterns from run_codebase_consolidation_2_production_deploy.sh + deploy_hardening.sh.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/deploy_hardening.sh
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"

APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
TARGET_SHA="${1:-}"
TS="$(date -u +%Y%m%d_%H%M%S)"
MANIFEST_DIR="${APP}/artifacts/deploy_manifests"
BACKUPS="${APP}/data/backups"
FRONTEND_DIST="/var/www/worldcup/frontend/dist"
PREVIOUS_SHA=""
SQLITE_BACKUP=""
SQLITE_SHA256=""
FRONTEND_BACKUP=""
DEPLOY_FAILED=0

deploy_init "production_deploy_safe" "${TARGET_SHA:-none}"

fail_deploy() {
  DEPLOY_FAILED=1
  deploy_log "DEPLOY_FAIL: $*"
  if [[ -n "${PREVIOUS_SHA}" ]]; then
    deploy_log "attempting controlled code rollback to ${PREVIOUS_SHA} (no DB restore)"
    bash "${SCRIPT_DIR}/production_rollback.sh" "${PREVIOUS_SHA}" "${FRONTEND_BACKUP}" || deploy_log "rollback script failed — operator intervention required"
  fi
  deploy_finish_fail "deploy"
  exit 1
}

run_py() {
  sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
    "cd ${APP} && set -a && source .env.production 2>/dev/null || true && set +a && .venv/bin/python $*"
}

if [[ -z "${TARGET_SHA}" ]]; then
  fail_deploy "target SHA required as first argument"
fi

deploy_acquire_lock || exit 1
trap 'deploy_release_lock' EXIT

cd "${APP}" || fail_deploy "cannot cd ${APP}"
PREVIOUS_SHA="$(git rev-parse HEAD)"

bash "${SCRIPT_DIR}/production_preflight.sh" "${TARGET_SHA}" || fail_deploy "preflight failed"

mkdir -p "${MANIFEST_DIR}" "${BACKUPS}"

# --- Backup gate ---
deploy_run_step "backup_commit_record" bash -c "echo '${PREVIOUS_SHA}' > '${BACKUPS}/pre_deploy_commit_${TS}.txt'"

if [[ -f "${APP}/scripts/backup_sqlite.sh" ]]; then
  deploy_run_step "backup_sqlite" bash -c "KEEP_BACKUPS=20 bash '${APP}/scripts/backup_sqlite.sh'"
  SQLITE_PATH="${SQLITE_PATH:-data/football_intelligence.db}"
  if [[ -f "${APP}/${SQLITE_PATH}" ]]; then
    SQLITE_BACKUP="${BACKUPS}/football_intelligence_before_code_deploy_${TS}.db"
    deploy_run_step "backup_sqlite_deploy_copy" bash -c "cp -a '${APP}/${SQLITE_PATH}' '${SQLITE_BACKUP}'"
    SQLITE_SHA256="$(sha256sum "${SQLITE_BACKUP}" | awk '{print $1}')"
  fi
fi

if [[ -d "${FRONTEND_DIST}" ]]; then
  FRONTEND_BACKUP="${BACKUPS}/frontend_dist_before_deploy_${TS}"
  deploy_run_step "backup_frontend_dist" bash -c "mkdir -p '${FRONTEND_BACKUP}' && rsync -a '${FRONTEND_DIST}/' '${FRONTEND_BACKUP}/'"
fi

SERVICE_BEFORE="$(systemctl is-active worldcup-api 2>/dev/null || echo unknown)"

MANIFEST="${MANIFEST_DIR}/deploy_${TS}.json"
python3 - <<PY
import json
from pathlib import Path
payload = {
    "deployment_id": "${DEPLOY_SESSION_ID}",
    "timestamp_utc": "${TS}",
    "old_sha": "${PREVIOUS_SHA}",
    "target_sha": "${TARGET_SHA}",
    "sqlite_backup": "${SQLITE_BACKUP}",
    "sqlite_sha256": "${SQLITE_SHA256}",
    "frontend_backup": "${FRONTEND_BACKUP}",
    "service_state_before": "${SERVICE_BEFORE}",
}
Path("${MANIFEST}").write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

deploy_log "backup manifest written: ${MANIFEST}"

# --- Safe code update (ff-only) ---
deploy_run_step "git_fetch" git fetch origin main
deploy_run_step "git_ff_only" git merge --ff-only "${TARGET_SHA}"

HEAD_AFTER="$(git rev-parse HEAD)"
if [[ "${HEAD_AFTER}" != "${TARGET_SHA}" ]]; then
  fail_deploy "HEAD after merge (${HEAD_AFTER}) does not match target (${TARGET_SHA})"
fi

# --- Backend validation ---
deploy_run_step "compileall" run_py -m compileall worldcup_predictor scripts -q
deploy_run_step "validate_strict_live" run_py scripts/validate_strict_live_odds_refresh_fix.py
if [[ -f "${APP}/scripts/validate_phase1_ssh_scaffold.py" ]]; then
  deploy_run_step "validate_phase1_ssh" run_py scripts/validate_phase1_ssh_scaffold.py
fi

# --- Frontend (only if base44-d changed) ---
if git diff --name-only "${PREVIOUS_SHA}".."${HEAD_AFTER}" 2>/dev/null | grep -q '^base44-d/'; then
  deploy_run_step "frontend_build" bash -c "
    cd '${APP}/base44-d' && \
    if [[ -f package-lock.json ]]; then npm ci; else npm install; fi && \
    npm run build
  "
  deploy_run_step "frontend_deploy" bash -c "
    rsync -a '${APP}/base44-d/dist/' '${FRONTEND_DIST}/' && \
    chown -R www-data:www-data '${FRONTEND_DIST}' 2>/dev/null || true
  "
else
  deploy_log "frontend unchanged — skip build"
fi

# --- Alembic / schema (forward only, when migrations present in diff) ---
if git diff --name-only "${PREVIOUS_SHA}".."${HEAD_AFTER}" 2>/dev/null | grep -qE '^alembic/'; then
  deploy_run_step "alembic_upgrade" run_py -m alembic upgrade head
fi

# --- Service restart (fixed unit only) ---
OPS_RESTART="${APP}/scripts/ops/worldcup_service_restart.sh"
if [[ -x "${OPS_RESTART}" ]]; then
  deploy_run_step "service_restart" sudo bash "${OPS_RESTART}"
else
  deploy_run_step "service_restart" sudo systemctl restart worldcup-api
fi

deploy_run_step "application_health" bash "${SCRIPT_DIR}/production_health_check.sh"

python3 - <<PY
import json
from pathlib import Path
p = Path("${MANIFEST}")
data = json.loads(p.read_text(encoding="utf-8"))
data.update({
    "deployed_sha": "${HEAD_AFTER}",
    "service_state_after": "$(systemctl is-active worldcup-api 2>/dev/null || echo unknown)",
    "result": "DEPLOY_OK",
})
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

deploy_finish_ok
echo "DEPLOY_OK sha=${HEAD_AFTER} manifest=${MANIFEST}"
