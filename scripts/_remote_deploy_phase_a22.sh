#!/usr/bin/env bash
# Phase A22 — Elite Shadow autonomous runtime production deploy (server-side)
set -eu
APP=/opt/worldcup-predictor
cd "$APP"
source .venv/bin/activate
export APP_ENV=production

echo "=== BACKUP ==="
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="$APP/backups/phase-a22-$TS"
mkdir -p "$BACKUP"
cp -a data/shadow "$BACKUP/" 2>/dev/null || true
cp -a deployment/systemd/worldcup-elite-shadow.service "$BACKUP/" 2>/dev/null || true
cp -a deployment/systemd/worldcup-elite-shadow.timer "$BACKUP/" 2>/dev/null || true
git rev-parse HEAD > "$BACKUP/commit.txt" 2>/dev/null || true

echo "=== EXTRACT ==="
tar xzf /tmp/phase_a22_deploy.tar.gz -C "$APP"

echo "=== VALIDATE (local) ==="
python scripts/validate_phase_a22_shadow_runtime.py | tee "$BACKUP/validate.log"

echo "=== SYSTEMD ==="
cp deployment/systemd/worldcup-elite-shadow.service /etc/systemd/system/
cp deployment/systemd/worldcup-elite-shadow.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable worldcup-elite-shadow.timer
systemctl start worldcup-elite-shadow.timer

echo "=== FRONTEND ==="
if [ -d /tmp/phase_a22_dist ]; then
  rsync -a --delete /tmp/phase_a22_dist/ /var/www/worldcup/frontend/dist/
  chown -R www-data:www-data /var/www/worldcup/frontend/dist/ 2>/dev/null || true
fi

echo "=== RESTART API ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api

echo "=== MANUAL SHADOW CYCLE ==="
BEFORE_P=$(wc -l < data/shadow/elite_orchestrator_predictions.jsonl 2>/dev/null || echo 0)
BEFORE_E=$(wc -l < data/shadow/elite_orchestrator_evaluations.jsonl 2>/dev/null || echo 0)
BEFORE_R=$(wc -l < data/shadow/root_cause_store/knowledge_records.jsonl 2>/dev/null || echo 0)
python main.py elite_shadow_once | tee "$BACKUP/shadow_cycle.log"
AFTER_P=$(wc -l < data/shadow/elite_orchestrator_predictions.jsonl 2>/dev/null || echo 0)
AFTER_E=$(wc -l < data/shadow/elite_orchestrator_evaluations.jsonl 2>/dev/null || echo 0)
AFTER_R=$(wc -l < data/shadow/root_cause_store/knowledge_records.jsonl 2>/dev/null || echo 0)
echo "predictions: $BEFORE_P -> $AFTER_P"
echo "evaluations: $BEFORE_E -> $AFTER_E"
echo "root_cause: $BEFORE_R -> $AFTER_R"

echo "=== TIMER STATUS ==="
systemctl is-active worldcup-elite-shadow.timer
systemctl list-timers worldcup-elite-shadow.timer --no-pager | head -5

echo "=== SMOKE ==="
bash "$APP/scripts/deploy_phase_a22_smoke.sh" | tee "$BACKUP/smoke.log"
echo DEPLOY_OK
