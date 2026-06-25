#!/usr/bin/env bash
# Phase 51F — production deploy: EGIE auto evaluation systemd timer
set -euo pipefail

APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/deploy-phase51f-${TS}"
TARBALL="${1:-/tmp/phase51f_deploy.tar.gz}"

echo "=== Phase 51F Production Deploy (EGIE Auto Evaluation) ==="
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

if [ -f /etc/systemd/system/egie-goal-timing-evaluation.timer ]; then
  cp -a /etc/systemd/system/egie-goal-timing-evaluation.timer "${BACKUP}/" 2>/dev/null || true
  cp -a /etc/systemd/system/egie-goal-timing-evaluation.service "${BACKUP}/" 2>/dev/null || true
fi

echo "=== 2. Extract deploy tarball ==="
tar xzf "${TARBALL}" -C "${APP}"

chmod +x scripts/install_phase51f_egie_eval_timer.sh 2>/dev/null || true
chmod +x scripts/deploy_phase51f_smoke.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/install_phase51f_egie_eval_timer.sh 2>/dev/null || true
sed -i 's/\r$//' scripts/deploy_phase51f_smoke.sh 2>/dev/null || true

chown -R www-data:www-data "${APP}/worldcup_predictor" 2>/dev/null || true

echo "=== 3. Restart API (evaluation routes only) ==="
systemctl restart worldcup-api
sleep 5
systemctl is-active worldcup-api

echo "=== 4. Install systemd timer ==="
bash scripts/install_phase51f_egie_eval_timer.sh

echo "=== 5. Manual job run ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python main.py egie-goal-timing-evaluation --limit 200 --max-api-calls 20" \
  2>&1 | tee "${BACKUP}/manual_job.log" | tail -20

echo "=== 6. Validation ==="
sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source .env.production && set +a && .venv/bin/python scripts/validate_phase51f_egie_auto_evaluation.py" \
  2>&1 | tee "${BACKUP}/validate_51f.log" | tail -30

echo "=== 7. Smoke ==="
bash scripts/deploy_phase51f_smoke.sh 2>&1 | tee "${BACKUP}/smoke.log"

echo "BACKUP_PATH=${BACKUP}"
echo "DEPLOY_OK"
