#!/usr/bin/env bash
# Phase A14 — hourly prediction prefetch (systemd timer entry)
set -eu
APP=/opt/worldcup-predictor
cd "$APP"
source .venv/bin/activate 2>/dev/null || true
python main.py prefetch-predictions --window-days "${PREFETCH_WINDOW_DAYS:-7}" --max-per-cycle "${PREFETCH_MAX_PER_CYCLE:-24}"
