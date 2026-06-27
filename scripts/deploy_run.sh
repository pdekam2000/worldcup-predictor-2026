#!/usr/bin/env bash
# Phase A21B — detached deploy launcher (survives SSH disconnect).
# Usage: deploy_run.sh [--foreground] [--resume SESSION_ID] <deploy_script> [args...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FOREGROUND=0
RESUME_SESSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground|-f)
      FOREGROUND=1
      shift
      ;;
    --resume|-r)
      RESUME_SESSION="${2:-}"
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 1 ]]; then
  echo "Usage: deploy_run.sh [--foreground] [--resume SESSION] <deploy_script> [args...]" >&2
  exit 2
fi

DEPLOY_SCRIPT="$1"
shift
DEPLOY_ARGS=("$@")

if [[ ! -f "${DEPLOY_SCRIPT}" ]]; then
  echo "Deploy script not found: ${DEPLOY_SCRIPT}" >&2
  exit 2
fi

DEPLOY_APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR:-${DEPLOY_APP}/logs/deploy}"
mkdir -p "${DEPLOY_LOG_DIR}"

LABEL="$(basename "${DEPLOY_SCRIPT}" .sh)"
STAMP="$(date -u +%Y%m%d_%H%M%S 2>/dev/null || date +%Y%m%d_%H%M%S)"
SESSION="${RESUME_SESSION:-${STAMP}_${LABEL}}"
LOG_FILE="${DEPLOY_LOG_DIR}/deploy_${SESSION}.log"
PID_FILE="${DEPLOY_LOG_DIR}/deploy_${SESSION}.pid"
WRAPPER_LOG="${DEPLOY_LOG_DIR}/wrapper_${SESSION}.log"

export WC_DEPLOY_DETACHED=1
export DEPLOY_SESSION_ID="${SESSION}"
export DEPLOY_RESUME_SESSION="${RESUME_SESSION}"
export DEPLOY_LOG_FILE="${LOG_FILE}"
export DEPLOY_FOREGROUND="${FOREGROUND}"

_run_body() {
  set -euo pipefail
  echo "[$(_ts)] Wrapper child PID=$$ session=${SESSION}" >> "${WRAPPER_LOG}"
  exec bash "${DEPLOY_SCRIPT}" "${DEPLOY_ARGS[@]}"
}

_ts() {
  date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ"
}

if [[ "${FOREGROUND}" -eq 1 ]] || [[ -n "${WC_DEPLOY_CHILD:-}" ]]; then
  export WC_DEPLOY_CHILD=1
  _run_body
fi

# Already detached — avoid double launch
if [[ -n "${WC_DEPLOY_LAUNCHED:-}" ]]; then
  export WC_DEPLOY_CHILD=1
  _run_body
fi

echo "[$(_ts)] Launching detached deploy session=${SESSION}" | tee -a "${WRAPPER_LOG}"
echo "${SESSION}" > "${DEPLOY_LOG_DIR}/.latest_session"

if command -v systemd-run >/dev/null 2>&1; then
  UNIT="worldcup-deploy-${STAMP}"
  echo "[$(_ts)] Using systemd-run unit=${UNIT}" >> "${WRAPPER_LOG}"
  systemd-run \
    --unit="${UNIT}" \
    --description="WorldCup Predictor deploy ${LABEL}" \
    --collect \
    --setenv=WC_DEPLOY_DETACHED=1 \
    --setenv=WC_DEPLOY_CHILD=1 \
    --setenv=WC_DEPLOY_LAUNCHED=1 \
    --setenv=DEPLOY_SESSION_ID="${SESSION}" \
    --setenv=DEPLOY_RESUME_SESSION="${RESUME_SESSION}" \
    --setenv=DEPLOY_LOG_FILE="${LOG_FILE}" \
    --setenv=DEPLOY_APP="${DEPLOY_APP}" \
    --setenv=DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR}" \
    bash -lc "echo $$ > '${PID_FILE}'; bash '${DEPLOY_SCRIPT}' $(printf '%q ' "${DEPLOY_ARGS[@]}") >> '${LOG_FILE}' 2>&1; ec=\$?; echo \"[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] exit=\$ec\" >> '${LOG_FILE}'; exit \$ec"
  echo "DEPLOY_LAUNCHED_OK session=${SESSION} mode=systemd-run unit=${UNIT}"
  echo "LOG=${LOG_FILE}"
  echo "STATUS=${DEPLOY_LOG_DIR}/deploy_${SESSION}.status.json"
  echo "PID_FILE=${PID_FILE}"
  exit 0
fi

# Fallback: nohup
echo "[$(_ts)] Using nohup fallback" >> "${WRAPPER_LOG}"
nohup bash -lc "
  export WC_DEPLOY_DETACHED=1 WC_DEPLOY_CHILD=1 WC_DEPLOY_LAUNCHED=1
  export DEPLOY_SESSION_ID='${SESSION}'
  export DEPLOY_RESUME_SESSION='${RESUME_SESSION}'
  export DEPLOY_LOG_FILE='${LOG_FILE}'
  export DEPLOY_APP='${DEPLOY_APP}'
  export DEPLOY_LOG_DIR='${DEPLOY_LOG_DIR}'
  echo \$\$ > '${PID_FILE}'
  bash '${DEPLOY_SCRIPT}' $(printf '%q ' "${DEPLOY_ARGS[@]}") >> '${LOG_FILE}' 2>&1
  ec=\$?
  echo \"[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] exit=\$ec\" >> '${LOG_FILE}'
  exit \$ec
" >> "${WRAPPER_LOG}" 2>&1 &
WRAP_PID=$!
echo "${WRAP_PID}" > "${PID_FILE}"
disown "${WRAP_PID}" 2>/dev/null || true
echo "DEPLOY_LAUNCHED_OK session=${SESSION} mode=nohup pid=${WRAP_PID}"
echo "LOG=${LOG_FILE}"
echo "STATUS=${DEPLOY_LOG_DIR}/deploy_${SESSION}.status.json"
echo "PID_FILE=${PID_FILE}"
exit 0
