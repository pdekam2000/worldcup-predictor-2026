#!/usr/bin/env bash
# Phase A21B — shared deploy hardening primitives (lock, logs, resume, status).
# Source from production deploy scripts; do not execute directly.

if [[ -n "${WC_DEPLOY_HARDENING_LOADED:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi
WC_DEPLOY_HARDENING_LOADED=1

DEPLOY_APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR:-${DEPLOY_APP}/logs/deploy}"
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-${DEPLOY_LOG_DIR}/.deploy.lock}"
DEPLOY_STATUS_DIR="${DEPLOY_STATUS_DIR:-${DEPLOY_LOG_DIR}}"
DEPLOY_BACKUP_ROOT="${DEPLOY_BACKUP_ROOT:-/opt/worldcup-backups}"

_ts() {
  date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ"
}

deploy_log() {
  local msg="[$(_ts)] $*"
  echo "$msg"
  if [[ -n "${DEPLOY_LOG_FILE:-}" ]]; then
    mkdir -p "$(dirname "${DEPLOY_LOG_FILE}")"
    echo "$msg" >> "${DEPLOY_LOG_FILE}"
  fi
}

deploy_session_id() {
  if [[ -n "${DEPLOY_SESSION_ID:-}" ]]; then
    echo "${DEPLOY_SESSION_ID}"
    return
  fi
  local label="${1:-deploy}"
  DEPLOY_SESSION_ID="$(date -u +%Y%m%d_%H%M%S)_${label}"
  export DEPLOY_SESSION_ID
  echo "${DEPLOY_SESSION_ID}"
}

deploy_init() {
  local label="${1:-deploy}"
  shift || true
  local session
  session="$(deploy_session_id "${label}")"
  mkdir -p "${DEPLOY_LOG_DIR}" "${DEPLOY_STATUS_DIR}" "${DEPLOY_BACKUP_ROOT}"

  if [[ -n "${DEPLOY_RESUME_SESSION:-}" ]]; then
    session="${DEPLOY_RESUME_SESSION}"
    DEPLOY_SESSION_ID="${session}"
    export DEPLOY_SESSION_ID
  fi

  DEPLOY_LOG_FILE="${DEPLOY_LOG_DIR}/deploy_${session}.log"
  DEPLOY_STATUS_FILE="${DEPLOY_STATUS_DIR}/deploy_${session}.status.json"
  DEPLOY_CHECKPOINT_FILE="${DEPLOY_LOG_DIR}/deploy_${session}.checkpoint"
  export DEPLOY_LOG_FILE DEPLOY_STATUS_FILE DEPLOY_CHECKPOINT_FILE

  deploy_log "=== Deploy session ${session} (${label}) ==="
  deploy_log "Args: $*"
  deploy_write_status "running" "init" "" ""
}

deploy_write_status() {
  local state="$1"
  local step="$2"
  local message="${3:-}"
  local rollback="${4:-}"
  [[ -n "${DEPLOY_STATUS_FILE:-}" ]] || return 0
  local pid="${$}"
  local started="${DEPLOY_STARTED_AT:-$(_ts)}"
  DEPLOY_STARTED_AT="${started}"
  export DEPLOY_STARTED_AT
  cat > "${DEPLOY_STATUS_FILE}" <<EOF
{
  "session_id": "${DEPLOY_SESSION_ID:-unknown}",
  "state": "${state}",
  "current_step": "${step}",
  "message": "${message}",
  "pid": ${pid},
  "started_at": "${started}",
  "updated_at": "$(_ts)",
  "log_file": "${DEPLOY_LOG_FILE:-}",
  "checkpoint_file": "${DEPLOY_CHECKPOINT_FILE:-}",
  "rollback": "${rollback}",
  "deploy_label": "${DEPLOY_LABEL:-deploy}"
}
EOF
  deploy_log "STATUS ${state} step=${step} ${message}"
}

deploy_acquire_lock() {
  mkdir -p "$(dirname "${DEPLOY_LOCK_FILE}")"
  exec 9>"${DEPLOY_LOCK_FILE}"
  if ! flock -n 9; then
    local holder=""
    if [[ -f "${DEPLOY_LOCK_FILE}" ]]; then
      holder="$(tr -d '\n' < "${DEPLOY_LOCK_FILE}" 2>/dev/null || true)"
    fi
    deploy_log "ERROR: Another deploy is in progress (lock held: ${holder:-unknown})"
    deploy_write_status "blocked" "lock" "duplicate deploy blocked" "${DEPLOY_ROLLBACK_HINT:-}"
    return 1
  fi
  echo "${DEPLOY_SESSION_ID:-$$} pid=$$" >&9
  deploy_log "Lock acquired: ${DEPLOY_LOCK_FILE}"
  return 0
}

deploy_release_lock() {
  flock -u 9 2>/dev/null || true
  deploy_log "Lock released"
}

deploy_step_done() {
  local step="$1"
  [[ -n "${DEPLOY_CHECKPOINT_FILE:-}" ]] || return 0
  if [[ -f "${DEPLOY_CHECKPOINT_FILE}" ]] && grep -qx "${step}" "${DEPLOY_CHECKPOINT_FILE}" 2>/dev/null; then
    return 0
  fi
  echo "${step}" >> "${DEPLOY_CHECKPOINT_FILE}"
}

deploy_step_completed() {
  local step="$1"
  [[ -f "${DEPLOY_CHECKPOINT_FILE:-}" ]] || return 1
  grep -qx "${step}" "${DEPLOY_CHECKPOINT_FILE}" 2>/dev/null
}

deploy_run_step() {
  local step="$1"
  shift
  if deploy_step_completed "${step}"; then
    deploy_log "SKIP (already done): ${step}"
    deploy_write_status "running" "${step}" "skipped-resume" "${DEPLOY_ROLLBACK_HINT:-}"
    return 0
  fi
  deploy_log "STEP START: ${step}"
  deploy_write_status "running" "${step}" "in_progress" "${DEPLOY_ROLLBACK_HINT:-}"
  if "$@"; then
    deploy_step_done "${step}"
    deploy_log "STEP OK: ${step}"
    return 0
  fi
  deploy_log "STEP FAILED: ${step}"
  deploy_write_status "failed" "${step}" "step failed" "${DEPLOY_ROLLBACK_HINT:-}"
  return 1
}

deploy_finish_ok() {
  deploy_write_status "ok" "complete" "DEPLOY_OK" "${DEPLOY_ROLLBACK_HINT:-}"
  deploy_log "=== DEPLOY_OK ==="
  deploy_log "Status file: ${DEPLOY_STATUS_FILE}"
}

deploy_finish_fail() {
  local step="${1:-unknown}"
  deploy_write_status "failed" "${step}" "deploy failed" "${DEPLOY_ROLLBACK_HINT:-}"
  deploy_log "=== DEPLOY_FAILED ==="
}

deploy_record_rollback() {
  local hint="$1"
  DEPLOY_ROLLBACK_HINT="${hint}"
  export DEPLOY_ROLLBACK_HINT
  deploy_write_status "${DEPLOY_STATE:-running}" "${DEPLOY_CURRENT_STEP:-backup}" "${DEPLOY_MESSAGE:-}" "${hint}"
}
