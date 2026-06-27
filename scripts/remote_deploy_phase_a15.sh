#!/usr/bin/env bash
# Phase A15 — PredOps production deploy
set -eu
APP=/opt/worldcup-predictor
cd "$APP"
source .venv/bin/activate
export APP_ENV=production

echo "=== BACKUP ==="
TS=$(date -u +%Y%m%d-%H%M%S)
mkdir -p "$APP/backups/phase-a15-$TS"
cp -a data/football_intelligence.db "$APP/backups/phase-a15-$TS/" 2>/dev/null || true
cp -a /var/www/worldcup/frontend/dist "$APP/backups/phase-a15-$TS/frontend_dist" 2>/dev/null || true
git rev-parse HEAD > "$APP/backups/phase-a15-$TS/commit.txt" 2>/dev/null || true

echo "=== EXTRACT ==="
tar xzf /tmp/phase_a15_deploy.tar.gz -C "$APP"

echo "=== MIGRATE (SQLite schema) ==="
python -c "from worldcup_predictor.database.repository import FootballIntelligenceRepository; from worldcup_predictor.database.migrations import ensure_schema_compat; r=FootballIntelligenceRepository(); ensure_schema_compat(r._conn); print('schema_ok')"

echo "=== BACKFILL SNAPSHOTS ==="
python main.py predops-run --backfill || true

echo "=== FRONTEND ==="
rsync -a --delete /tmp/phase_a15_dist/ /var/www/worldcup/frontend/dist/
chown -R www-data:www-data /var/www/worldcup/frontend/dist/ 2>/dev/null || true

echo "=== SYSTEMD ==="
cp deployment/systemd/worldcup-prediction-prefetch.service /etc/systemd/system/
systemctl daemon-reload

echo "=== RESTART API ==="
systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api

echo "=== DRY RUN ==="
python main.py predops-run --dry-run --max-jobs 0

echo "=== SMALL RUN ==="
python main.py predops-run --max-jobs 4

echo "=== SMOKE ==="
curl -s -o /dev/null -w "health=%{http_code}\n" https://footballpredictor.it.com/api/health
curl -s -o /dev/null -w "coverage=%{http_code}\n" https://footballpredictor.it.com/api/predops/coverage
curl -s -o /dev/null -w "combo=%{http_code}\n" https://footballpredictor.it.com/api/predops/combo-readiness
curl -s -o /dev/null -w "predops_page=%{http_code}\n" https://footballpredictor.it.com/admin/predops
echo DEPLOY_OK
