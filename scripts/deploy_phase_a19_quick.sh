#!/usr/bin/env bash
set -euo pipefail
APP=/opt/worldcup-predictor
cd "$APP"
tar xzf /tmp/phase_a19_deploy.tar.gz -C "$APP"
.venv/bin/python -c "from worldcup_predictor.database.repository import FootballIntelligenceRepository; from worldcup_predictor.database.migrations import ensure_schema_compat; ensure_schema_compat(FootballIntelligenceRepository()._conn)"
cd "$APP/base44-d"
npm ci --silent 2>/dev/null || npm install --silent
npm run build
rsync -a --delete dist/ /var/www/worldcup/frontend/dist/
systemctl restart worldcup-api
sleep 6
systemctl is-active --quiet worldcup-api
cd "$APP"
.venv/bin/python -c "from worldcup_predictor.ai_assistant.scheduler import run_alert_scan; print(run_alert_scan())"
nginx -t
systemctl reload nginx
bash "$APP/scripts/deploy_phase_a19_smoke.sh"
echo DEPLOY_OK
