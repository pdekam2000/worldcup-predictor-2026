#!/usr/bin/env bash
# Phase 63A — settings drift fix (production)
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase63a-settings-${TS}"

mkdir -p "${BACKUP}"
cp -a "${APP}/worldcup_predictor/config/settings.py" "${BACKUP}/settings.py.pre"
git -C "${APP}" rev-parse HEAD > "${BACKUP}/pre_commit.txt" 2>/dev/null || true

python3 "${APP}/scripts/apply_phase63a_settings_drift_fix.py"
grep -q UNIFIED_ENGINE_PUBLIC "${APP}/worldcup_predictor/config/settings.py"

systemctl restart worldcup-api
sleep 5
systemctl is-active --quiet worldcup-api

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_hotfix_market_level_result_evaluation.py" \
  | tee "${BACKUP}/validate.log"

echo "BACKUP_PATH=${BACKUP}"
