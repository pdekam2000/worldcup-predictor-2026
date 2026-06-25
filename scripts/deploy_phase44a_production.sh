#!/usr/bin/env bash
# Phase 44A — production deploy: Auto Evaluation + systemd timer
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase44a-${TS}"
TARBALL="${1:-/tmp/phase44a_deploy.tar.gz}"

echo "=== Phase 44A Production Deploy (Auto Evaluation) ==="
echo "Backup: ${BACKUP}"
mkdir -p "${BACKUP}"
chown www-data:www-data "${BACKUP}" 2>/dev/null || chmod 775 "${BACKUP}"

cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt" 2>/dev/null || echo "unknown" > "${BACKUP}/pre_deploy_commit.txt"
echo "Pre-deploy commit: $(cat "${BACKUP}/pre_deploy_commit.txt")"

if [ -f data/football_intelligence.db ]; then
  cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db"
  echo "SQLite backed up"
fi

if [ -f .env.production ]; then
  cp -a .env.production "${BACKUP}/env.production"
fi

tar czf "${BACKUP}/repo_snapshot_pre.tar.gz" \
  worldcup_predictor/automation/worldcup_background/ \
  worldcup_predictor/database/repository.py \
  worldcup_predictor/cli/commands.py \
  worldcup_predictor/api/routes/admin_accuracy.py \
  main.py \
  deployment/systemd/worldcup-evaluate-results.service \
  deployment/systemd/worldcup-evaluate-results.timer \
  scripts/install_phase44a_eval_timer.sh \
  scripts/validate_phase44a_auto_evaluation.py \
  2>/dev/null || true

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

chmod +x scripts/install_phase44a_eval_timer.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/install_phase44a_eval_timer.sh 2>/dev/null || true

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart API (no prediction engine change) ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 4. Install systemd timer ==="
bash scripts/install_phase44a_eval_timer.sh

echo "=== 5. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase44a_auto_evaluation.py" \
  2>&1 | tee "${BACKUP}/validate_44a.log" | tail -30

echo "=== 6. Smoke ==="
bash scripts/deploy_phase44a_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
