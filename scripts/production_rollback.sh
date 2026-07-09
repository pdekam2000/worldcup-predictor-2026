#!/usr/bin/env bash
# Phase 2 — controlled code rollback (no automatic DB restore on app failure).
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/deploy_hardening.sh
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"

APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
PREVIOUS_SHA="${1:-}"
FRONTEND_BACKUP="${2:-}"
RESTORE_DB="${RESTORE_DB:-0}"

deploy_init "rollback" "${PREVIOUS_SHA:-none}"

fail() {
  deploy_log "ROLLBACK_FAIL: $*"
  deploy_finish_fail "rollback"
  exit 1
}

if [[ -z "${PREVIOUS_SHA}" ]]; then
  fail "previous known-good SHA required as first argument"
fi

if [[ "${RESTORE_DB}" == "1" ]]; then
  deploy_log "WARN: RESTORE_DB=1 — DB rollback is explicit operator action only"
  if [[ -z "${SQLITE_BACKUP_PATH:-}" ]]; then
    fail "RESTORE_DB=1 requires SQLITE_BACKUP_PATH"
  fi
fi

cd "${APP}" || fail "cannot cd ${APP}"

CURRENT_SHA="$(git rev-parse HEAD)"
DIRTY="$(git status --porcelain)"
if [[ -n "${DIRTY}" ]]; then
  fail "production tree is dirty — resolve before rollback"
fi

if ! git cat-file -e "${PREVIOUS_SHA}^{commit}" 2>/dev/null; then
  fail "previous SHA not found: ${PREVIOUS_SHA}"
fi

deploy_log "rollback from ${CURRENT_SHA} to ${PREVIOUS_SHA}"

if ! git merge-base --is-ancestor "${PREVIOUS_SHA}" "${CURRENT_SHA}" 2>/dev/null; then
  fail "previous SHA is not an ancestor of current HEAD — refusing unsafe rollback"
fi

if ! git checkout "${PREVIOUS_SHA}"; then
  fail "git checkout to previous SHA failed"
fi

if [[ -n "${FRONTEND_BACKUP}" && -d "${FRONTEND_BACKUP}" ]]; then
  FRONTEND_DIST="/var/www/worldcup/frontend/dist"
  if [[ -d "${FRONTEND_DIST}" ]]; then
    deploy_log "restoring frontend dist from ${FRONTEND_BACKUP}"
    rsync -a --delete "${FRONTEND_BACKUP}/" "${FRONTEND_DIST}/" || fail "frontend restore failed"
  fi
fi

if [[ "${RESTORE_DB}" == "1" ]]; then
  SQLITE_PATH="${SQLITE_PATH:-data/football_intelligence.db}"
  deploy_log "explicit SQLite restore from ${SQLITE_BACKUP_PATH}"
  cp -a "${SQLITE_BACKUP_PATH}" "${APP}/${SQLITE_PATH}" || fail "SQLite restore failed"
fi

OPS_RESTART="${APP}/scripts/ops/worldcup_service_restart.sh"
if [[ -x "${OPS_RESTART}" ]]; then
  bash "${OPS_RESTART}" || fail "service restart after rollback failed"
else
  systemctl restart worldcup-api || fail "systemctl restart worldcup-api failed"
fi

bash "${APP}/scripts/production_health_check.sh" || fail "health check failed after rollback"

deploy_record_rollback "rolled_back_to=${PREVIOUS_SHA}"
deploy_finish_ok
echo "ROLLBACK_OK sha=${PREVIOUS_SHA}"
