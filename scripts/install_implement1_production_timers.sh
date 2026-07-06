#!/usr/bin/env bash
# IMPLEMENT-1 — install daily prediction + hourly results/evaluation timers
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
UNIT_SRC="${APP_DIR}/deployment/systemd"

if [[ ! -d "${UNIT_SRC}" ]]; then
  echo "Missing ${UNIT_SRC}" >&2
  exit 1
fi

for unit in worldcup-prediction-daily worldcup-results-hourly; do
  cp "${UNIT_SRC}/${unit}.service" /etc/systemd/system/
  cp "${UNIT_SRC}/${unit}.timer" /etc/systemd/system/
done

systemctl daemon-reload
systemctl enable worldcup-prediction-daily.timer
systemctl enable worldcup-results-hourly.timer
systemctl start worldcup-prediction-daily.timer
systemctl start worldcup-results-hourly.timer

systemctl status worldcup-prediction-daily.timer --no-pager || true
systemctl status worldcup-results-hourly.timer --no-pager || true
echo "IMPLEMENT-1 timers installed."
echo "Next runs:"
systemctl list-timers worldcup-prediction-daily.timer worldcup-results-hourly.timer --no-pager || true
