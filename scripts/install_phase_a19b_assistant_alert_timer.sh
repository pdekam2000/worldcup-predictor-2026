#!/usr/bin/env bash
# Phase A19B — install worldcup-assistant-alert-scan systemd timer
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
UNIT_SRC="${APP_DIR}/deployment/systemd"

if [[ ! -f "${UNIT_SRC}/worldcup-assistant-alert-scan.service" ]]; then
  echo "Missing ${UNIT_SRC}/worldcup-assistant-alert-scan.service" >&2
  exit 1
fi

cp "${UNIT_SRC}/worldcup-assistant-alert-scan.service" /etc/systemd/system/
cp "${UNIT_SRC}/worldcup-assistant-alert-scan.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now worldcup-assistant-alert-scan.timer
echo "=== Timer status ==="
systemctl status worldcup-assistant-alert-scan.timer --no-pager || true
echo "=== Next runs ==="
systemctl list-timers --all | grep assistant || true
echo "INSTALL_OK"
