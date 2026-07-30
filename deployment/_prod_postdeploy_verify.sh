#!/usr/bin/env bash
set -euo pipefail
systemctl is-active worldcup-api worldcup-gpt-actions nginx
curl -sS http://127.0.0.1:8000/api/health; echo
cd /opt/worldcup-predictor
.venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect("data/football_intelligence.db")
need = [
    "derived_historical_team_form_snapshots",
    "totals_market_shadow_snapshots",
    "lambda_v2_shadow_outputs",
    "alternate_totals_capture_status",
]
have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
print("tables", {t: (t in have) for t in need})
print("head", open("/opt/worldcup-predictor/backups/infra_deploy/20260730T165735Z/DEPLOYMENT_SUMMARY.txt").read())
PY
