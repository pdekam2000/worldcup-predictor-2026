#!/usr/bin/env bash
# Phase A19 — AI Watchlist & Smart Alerts (A21B hardened).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${WC_DEPLOY_CHILD:-}" ]] && [[ "${DEPLOY_FOREGROUND:-0}" != "1" ]]; then
  exec bash "${SCRIPT_DIR}/deploy_run.sh" "$0" "$@"
fi

# shellcheck source=lib/deploy_hardening.sh
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"

TARBALL="${1:-/tmp/phase_a19_deploy.tar.gz}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
STAMP="$(date -u +%Y%m%d_%H%M%S 2>/dev/null || date +%Y%m%d_%H%M%S)"
DEPLOY_LABEL="phase_a19"
DEPLOY_APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
BACKUP="${DEPLOY_APP}/backups/deploy-phase-a19-${STAMP}"

deploy_init "${DEPLOY_LABEL}" "${TARBALL}"
trap 'deploy_finish_fail "${DEPLOY_CURRENT_STEP:-unknown}"; deploy_release_lock' ERR
trap 'deploy_release_lock' EXIT

deploy_acquire_lock || exit 3
deploy_record_rollback "backup_dir=${BACKUP}"

step_backup() {
  mkdir -p "${BACKUP}"
  cd "${DEPLOY_APP}"
  git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo unknown > "${BACKUP}/pre_deploy_commit.txt"
  if [[ -f data/football_intelligence.db ]]; then
    cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db" 2>/dev/null || true
  fi
  if command -v pg_dump >/dev/null 2>&1 && [[ -n "${DATABASE_URL:-}" ]]; then
    pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres.sql" 2>/dev/null || true
  fi
  if [[ -d "${FRONTEND_DIST}" ]]; then
    cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
  fi
  tar czf "${BACKUP}/repo_pre_deploy.tar.gz" --exclude=node_modules --exclude=.git/objects --exclude=base44-d/dist . 2>/dev/null || true
}

step_extract() {
  tar xzf "${TARBALL}" -C "${DEPLOY_APP}"
}

step_migrate() {
  cd "${DEPLOY_APP}"
  .venv/bin/python -c "from worldcup_predictor.database.repository import FootballIntelligenceRepository; from worldcup_predictor.database.migrations import ensure_schema_compat; ensure_schema_compat(FootballIntelligenceRepository()._conn)"
}

step_frontend() {
  cd "${DEPLOY_APP}/base44-d"
  npm ci --silent 2>/dev/null || npm install --silent
  npm run build
  mkdir -p "${FRONTEND_DIST}"
  rsync -a --delete dist/ "${FRONTEND_DIST}/"
  chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true
}

step_restart() {
  systemctl restart worldcup-api
  sleep 6
  systemctl is-active --quiet worldcup-api
}

step_alert_scan() {
  cd "${DEPLOY_APP}"
  .venv/bin/python -c "from worldcup_predictor.ai_assistant.scheduler import run_alert_scan; print(run_alert_scan())" || true
}

step_nginx() {
  nginx -t
  systemctl reload nginx
}

step_smoke() {
  bash "${DEPLOY_APP}/scripts/deploy_phase_a19_smoke.sh"
}

deploy_run_step backup step_backup
deploy_run_step extract step_extract
deploy_run_step migrate step_migrate
deploy_run_step frontend step_frontend
deploy_run_step restart step_restart
deploy_run_step alert_scan step_alert_scan
deploy_run_step nginx step_nginx
deploy_run_step smoke step_smoke

deploy_finish_ok
exit 0
