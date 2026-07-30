#!/usr/bin/env bash
# Align production to package tip without remigrating or full FI copy.
set -euo pipefail
APP=/opt/worldcup-predictor
TARGET="${1:-4ee0a03}"
cd "$APP"
PRE=$(git rev-parse HEAD)
echo "pre=$PRE"
git fetch origin release/football-strength-shadow-infra-20260730T151432Z
git rev-parse "${TARGET}^{commit}" >/dev/null
# helpers-only tip: no migration re-run
git checkout --detach "$TARGET"
POST=$(git rev-parse HEAD)
echo "post=$POST"
# restart only if code helpers changed (safe)
systemctl restart worldcup-api worldcup-gpt-actions
sleep 3
systemctl is-active worldcup-api worldcup-gpt-actions nginx
curl -sS http://127.0.0.1:8000/api/health; echo
.venv/bin/python deployment/canonical_regression_probe.py --mode local \
  --out-md /tmp/parity_canonical_regression.md \
  --out-json /tmp/parity_canonical_regression.json
echo "parity_ok pre=$PRE post=$POST"
