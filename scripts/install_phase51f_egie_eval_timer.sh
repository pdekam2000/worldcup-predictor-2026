#!/usr/bin/env bash
# Phase 51F — install egie-goal-timing-evaluation systemd timer (operator run after approval)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
UNIT_SRC="${APP_DIR}/deployment/systemd"

if [[ ! -d "${UNIT_SRC}" ]]; then
  echo "Missing ${UNIT_SRC}" >&2
  exit 1
fi

for unit in egie-goal-timing-evaluation.service egie-goal-timing-evaluation.timer; do
  if [[ ! -f "${UNIT_SRC}/${unit}" ]]; then
    echo "Missing ${UNIT_SRC}/${unit}" >&2
    exit 1
  fi
done

cp "${UNIT_SRC}/egie-goal-timing-evaluation.service" /etc/systemd/system/
cp "${UNIT_SRC}/egie-goal-timing-evaluation.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable egie-goal-timing-evaluation.timer
systemctl start egie-goal-timing-evaluation.timer
systemctl status egie-goal-timing-evaluation.timer --no-pager || true
echo "Phase 51F timer installed. Next runs: systemctl list-timers egie-goal-timing-evaluation.timer"
