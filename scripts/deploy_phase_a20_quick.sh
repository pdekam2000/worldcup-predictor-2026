#!/usr/bin/env bash
# Phase A20 — Social trust deploy (A21B hardened).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${WC_DEPLOY_CHILD:-}" ]] && [[ "${DEPLOY_FOREGROUND:-0}" != "1" ]]; then
  exec bash "${SCRIPT_DIR}/deploy_run.sh" "$0" "$@"
fi

# shellcheck source=lib/deploy_hardening.sh
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"

TARBALL="${1:-/tmp/phase_a20_deploy.tar.gz}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
STAMP="$(date -u +%Y%m%d_%H%M%S 2>/dev/null || date +%Y%m%d_%H%M%S)"
DEPLOY_LABEL="phase_a20"
DEPLOY_APP="${DEPLOY_APP:-/opt/worldcup-predictor}"

deploy_init "${DEPLOY_LABEL}" "${TARBALL}"
trap 'deploy_finish_fail "${DEPLOY_CURRENT_STEP:-unknown}"; deploy_release_lock' ERR
trap 'deploy_release_lock' EXIT

deploy_acquire_lock || exit 3
deploy_record_rollback "commit=${DEPLOY_BACKUP_ROOT}/commit_pre_a20_${STAMP}.txt"

step_extract() {
  if [[ -f "${TARBALL}" ]]; then
    tar xzf "${TARBALL}" -C "${DEPLOY_APP}"
  fi
}

step_migrate() {
  cd "${DEPLOY_APP}"
  git rev-parse HEAD > "${DEPLOY_BACKUP_ROOT}/commit_pre_a20_${STAMP}.txt" 2>/dev/null || true
  .venv/bin/python -c "from worldcup_predictor.database.repository import FootballIntelligenceRepository; from worldcup_predictor.database.migrations import ensure_schema_compat; ensure_schema_compat(FootballIntelligenceRepository()._conn)"
}

step_frontend() {
  cd "${DEPLOY_APP}/base44-d"
  npm ci --silent 2>/dev/null || npm install --silent
  npm run build
  rsync -a --delete dist/ "${FRONTEND_DIST}/"
}

step_restart() {
  systemctl restart worldcup-api
  sleep 5
  systemctl is-active --quiet worldcup-api
}

step_nginx() {
  nginx -t && systemctl reload nginx
}

step_validate() {
  SKIP_FRONTEND_BUILD=1 "${DEPLOY_APP}/.venv/bin/python" "${DEPLOY_APP}/scripts/validate_phase_a20_social_trust.py"
}

step_smoke() {
  bash "${DEPLOY_APP}/scripts/deploy_phase_a20_smoke.sh"
}

deploy_run_step extract step_extract
deploy_run_step migrate step_migrate
deploy_run_step frontend step_frontend
deploy_run_step restart step_restart
deploy_run_step nginx step_nginx
deploy_run_step validate step_validate
deploy_run_step smoke step_smoke

deploy_finish_ok
exit 0
