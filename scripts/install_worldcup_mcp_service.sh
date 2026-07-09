#!/usr/bin/env bash
# Phase 3 — install worldcup-mcp systemd unit (root only).
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/worldcup-predictor}"
UNIT_SRC="${APP_ROOT}/deployment/systemd/worldcup-mcp.service"
UNIT_DST="/etc/systemd/system/worldcup-mcp.service"
AUDIT_DIR="/var/log/worldcup-mcp"
SERVICE_USER="worldcup-mcp"
BACKUP_SUFFIX="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root" >&2
  exit 1
fi

echo "==> Pre-flight"
whoami
hostname
pwd
if [[ -d "${APP_ROOT}/.git" ]]; then
  git -C "${APP_ROOT}" status --short | head -20 || true
  git -C "${APP_ROOT}" rev-parse HEAD || true
fi
systemctl is-active worldcup-api || true
df -h "${APP_ROOT}" || df -h /

if [[ -f "${UNIT_DST}" ]]; then
  cp -a "${UNIT_DST}" "${UNIT_DST}.bak.${BACKUP_SUFFIX}"
  echo "Backed up existing unit to ${UNIT_DST}.bak.${BACKUP_SUFFIX}"
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home "${APP_ROOT}" --shell /usr/sbin/nologin "${SERVICE_USER}"
  echo "Created service user ${SERVICE_USER}"
fi

install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${AUDIT_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${AUDIT_DIR}"

"${APP_ROOT}/.venv/bin/pip" install 'mcp>=1.27,<2'

install -m 0644 "${UNIT_SRC}" "${UNIT_DST}"
systemctl daemon-reload
systemctl enable worldcup-mcp.service

echo "==> Validating unit"
systemctl cat worldcup-mcp.service | head -40
"${APP_ROOT}/.venv/bin/python" "${APP_ROOT}/scripts/validate_phase3_mcp_prediction_server.py"

systemctl restart worldcup-mcp.service
sleep 2
systemctl is-active worldcup-mcp.service
systemctl is-active worldcup-api.service

echo "==> MCP install complete"
echo "Rollback: systemctl disable --now worldcup-mcp.service && mv ${UNIT_DST}.bak.${BACKUP_SUFFIX} ${UNIT_DST} && systemctl daemon-reload"
