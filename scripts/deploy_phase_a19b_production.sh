#!/usr/bin/env bash
# Phase A19B — deploy assistant alert timer
set -euo pipefail

APP=/opt/worldcup-predictor
TARBALL="${1:-/tmp/phase_a19b_deploy.tar.gz}"

echo "=== Phase A19B Deploy ==="
if [[ -f "${TARBALL}" ]]; then
  tar xzf "${TARBALL}" -C "${APP}"
fi

cd "${APP}"
.venv/bin/python -c "from worldcup_predictor.database.repository import FootballIntelligenceRepository; from worldcup_predictor.database.migrations import ensure_schema_compat; ensure_schema_compat(FootballIntelligenceRepository()._conn)"

echo "=== Install systemd timer ==="
bash scripts/install_phase_a19b_assistant_alert_timer.sh

echo "=== Manual scan smoke ==="
sudo -u www-data bash -lc "cd ${APP} && .venv/bin/python main.py assistant-alert-scan" || true

echo "=== Journal smoke ==="
journalctl -u worldcup-assistant-alert-scan.service -n 5 --no-pager 2>/dev/null || true

echo "=== Validation ==="
SKIP_FRONTEND_BUILD=1 .venv/bin/python scripts/validate_phase_a19b_assistant_alert_timer.py

echo "DEPLOY_OK"
