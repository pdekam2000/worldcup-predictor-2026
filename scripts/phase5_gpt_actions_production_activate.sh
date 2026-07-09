#!/usr/bin/env bash
# Phase 5 — GPT Actions production activation (Hetzner)
set -euo pipefail

APP_ROOT="/opt/worldcup-predictor"
BACKUP_DIR="${APP_ROOT}/backups/gpt_actions_phase5"
NGINX_SITE="/etc/nginx/sites-enabled/worldcup"
NGINX_CONF="/etc/nginx/nginx.conf"
ENV_DIR="/etc/worldcup-gpt-actions"
ENV_FILE="${ENV_DIR}/environment"
SERVICE="worldcup-gpt-actions"
LOG_DIR="/var/log/worldcup-gpt-actions"

log() { echo "[phase5] $*"; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root on production" >&2
    exit 1
  fi
}

preflight_backup() {
  mkdir -p "${BACKUP_DIR}"
  cp -a "${NGINX_SITE}" "${BACKUP_DIR}/nginx_before_phase5.conf" 2>/dev/null || true
  cp -a "/etc/systemd/system/${SERVICE}.service" "${BACKUP_DIR}/worldcup-gpt-actions.service.before_phase5" 2>/dev/null || true
  cd "${APP_ROOT}"
  git diff > "${BACKUP_DIR}/production_source_before_phase5.patch" || true
  log "Backups written to ${BACKUP_DIR}"
}

deploy_source() {
  cd "${APP_ROOT}"
  git fetch origin main
  git pull --ff-only origin main
  test -d worldcup_predictor/gpt_actions
  test -f deployment/systemd/worldcup-gpt-actions.service
  test -f deployment/nginx/gpt-actions-snippet.conf
}

ensure_user() {
  if ! id worldcup-gpt-actions >/dev/null 2>&1; then
    useradd --system --home /opt/worldcup-predictor --shell /usr/sbin/nologin worldcup-gpt-actions
  fi
  usermod -aG www-data worldcup-gpt-actions 2>/dev/null || true
  mkdir -p "${LOG_DIR}" "${APP_ROOT}/artifacts/gpt_actions_jobs"
  chown -R worldcup-gpt-actions:worldcup-gpt-actions "${LOG_DIR}" "${APP_ROOT}/artifacts/gpt_actions_jobs"
  chmod 750 "${LOG_DIR}"
  if command -v setfacl >/dev/null 2>&1; then
    setfacl -m u:worldcup-gpt-actions:r-- /opt/worldcup-predictor/.env.production 2>/dev/null || true
    DB="${APP_ROOT}/data/football_intelligence.db"
    if [[ -f "${DB}" ]]; then
      setfacl -m u:worldcup-gpt-actions:rw- "${DB}" 2>/dev/null || true
    fi
  fi
}

ensure_env() {
  mkdir -p "${ENV_DIR}"
  if [[ ! -f "${ENV_FILE}" ]]; then
    KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
    umask 077
    cat > "${ENV_FILE}" <<EOF
GPT_ACTIONS_API_KEY=${KEY}
GPT_ACTIONS_HOST=127.0.0.1
GPT_ACTIONS_PORT=8770
GPT_ACTIONS_AUDIT_LOG_PATH=${LOG_DIR}/audit.jsonl
GPT_ACTIONS_JOB_DIR=${APP_ROOT}/artifacts/gpt_actions_jobs
APP_ROOT=${APP_ROOT}
EOF
    chown root:worldcup-gpt-actions "${ENV_FILE}"
    chmod 640 "${ENV_FILE}"
    log "Created ${ENV_FILE} (key not printed)"
  else
    chown root:worldcup-gpt-actions "${ENV_FILE}"
    chmod 640 "${ENV_FILE}"
    log "Using existing ${ENV_FILE}"
  fi
}

install_systemd() {
  cp "${APP_ROOT}/deployment/systemd/worldcup-gpt-actions.service" "/etc/systemd/system/${SERVICE}.service"
  systemctl daemon-reload
  systemctl enable "${SERVICE}"
  systemctl restart "${SERVICE}"
  systemctl is-active --quiet "${SERVICE}"
}

validate_local_bind() {
  ss -ltnp | grep 8770 | grep 127.0.0.1 >/dev/null
  if ss -ltnp | grep 8770 | grep -E '0.0.0.0|\\*' >/dev/null; then
    echo "Forbidden public bind on 8770" >&2
    exit 1
  fi
}

ensure_nginx_zone() {
  if ! grep -q 'zone=gpt_actions' "${NGINX_CONF}"; then
    sed -i '/^http {/a \    limit_req_zone $binary_remote_addr zone=gpt_actions:10m rate=30r/m;' "${NGINX_CONF}"
  fi
}

install_nginx_snippet() {
  if grep -q '/api/gpt-actions/v1/' "${NGINX_SITE}"; then
    log "Nginx GPT Actions routes already present"
    return
  fi
  ensure_nginx_zone
  SNIP="${APP_ROOT}/deployment/nginx/gpt-actions-snippet.conf"
  # Insert before generic /api/ location
  awk -v snip="${SNIP}" '
    BEGIN { while ((getline line < snip) > 0) snippet = snippet line "\n" }
    /location \/api\/ \{/ && !done { print snippet; done=1 }
    { print }
  ' "${NGINX_SITE}" > "${NGINX_SITE}.phase5.tmp"
  mv "${NGINX_SITE}.phase5.tmp" "${NGINX_SITE}"
  nginx -t
  systemctl reload nginx
}

main() {
  require_root
  preflight_backup
  deploy_source
  ensure_user
  ensure_env
  install_systemd
  validate_local_bind
  install_nginx_snippet
  log "Phase 5 activation complete"
}

main "$@"
