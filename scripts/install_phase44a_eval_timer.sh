#!/usr/bin/env bash
# Phase 44A — install worldcup-evaluate-results systemd timer (operator run after approval)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
UNIT_SRC="${APP_DIR}/deployment/systemd"

if [[ ! -d "${UNIT_SRC}" ]]; then
  echo "Missing ${UNIT_SRC}" >&2
  exit 1
fi

cp "${UNIT_SRC}/worldcup-evaluate-results.service" /etc/systemd/system/
cp "${UNIT_SRC}/worldcup-evaluate-results.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable worldcup-evaluate-results.timer
systemctl start worldcup-evaluate-results.timer
systemctl status worldcup-evaluate-results.timer --no-pager || true
echo "Phase 44A timer installed. Next runs: systemctl list-timers worldcup-evaluate-results.timer"
