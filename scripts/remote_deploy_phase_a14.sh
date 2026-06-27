#!/usr/bin/env bash
set -eu
cd /opt/worldcup-predictor
source .venv/bin/activate
export APP_ENV=production

echo "=== EXTRACT ==="
tar xzf /tmp/phase_a14_deploy.tar.gz -C /opt/worldcup-predictor

echo "=== FRONTEND ==="
rsync -a --delete /tmp/phase_a14_dist/ /var/www/worldcup/frontend/dist/
chown -R www-data:www-data /var/www/worldcup/frontend/dist/ 2>/dev/null || true

echo "=== SYSTEMD ==="
cp deployment/systemd/worldcup-prediction-prefetch.service /etc/systemd/system/
cp deployment/systemd/worldcup-prediction-prefetch.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable worldcup-prediction-prefetch.timer

echo "=== RESTART API ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api

echo "=== BEFORE COVERAGE ==="
python - <<'PY'
from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report
import json
r = build_coverage_report(window_days=7)
print(json.dumps({"totals": r.get("totals"), "combo": r.get("combo_readiness")}, indent=2))
PY

echo "=== RUN PREFETCH ONCE (max 12) ==="
python main.py prefetch-predictions --window-days 7 --max-per-cycle 12

echo "=== AFTER COVERAGE ==="
python - <<'PY'
from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report
import json
from pathlib import Path
r = build_coverage_report(window_days=7)
out = {"totals": r.get("totals"), "combo": r.get("combo_readiness"), "competitions": r.get("competitions")}
print(json.dumps(out, indent=2))
Path("data/shadow/phase_a14_deploy_coverage.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
PY

state_path="data/shadow/prefetch_scheduler_state.json"
if [ -f "$state_path" ]; then
  echo "=== SCHEDULER STATE ==="
  cat "$state_path"
fi

echo "=== TIMER ==="
systemctl start worldcup-prediction-prefetch.timer
systemctl is-active worldcup-prediction-prefetch.timer

echo "=== SMOKE ==="
bash scripts/deploy_phase_a14_smoke.sh
echo DEPLOY_OK
