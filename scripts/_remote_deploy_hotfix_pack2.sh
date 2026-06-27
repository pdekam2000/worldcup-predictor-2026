#!/usr/bin/env bash
set -eu
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="$APP/backups/hotfix-pack2-$TS"
mkdir -p "$BACKUP"
cp -a /var/www/worldcup/frontend/dist "$BACKUP/frontend_dist" 2>/dev/null || true
cp -a "$APP/data/football_intelligence.db" "$BACKUP/football_intelligence.db" 2>/dev/null || true
git -C "$APP" rev-parse HEAD > "$BACKUP/commit.txt" 2>/dev/null || true

tar xzf /tmp/hotfix_pack2_deploy.tar.gz -C "$APP"
sed -i 's/\r$//' "$APP/scripts/deploy_hotfix_pack2_production.sh" "$APP/scripts/_remote_deploy_hotfix_pack2.sh" 2>/dev/null || true
bash "$APP/scripts/deploy_hotfix_pack2_production.sh" /tmp/hotfix_pack2_deploy.tar.gz | tee "$BACKUP/deploy.log"

curl -s -o /dev/null -w "picks=%{http_code}\n" "http://127.0.0.1:8000/api/goal-timing/picks?limit=3"
curl -s -o /dev/null -w "dashboard=%{http_code}\n" http://127.0.0.1:8000/api/goal-timing/dashboard
curl -s -o /dev/null -w "eval=%{http_code}\n" http://127.0.0.1:8000/api/matches/1489409/evaluation
curl -s -o /dev/null -w "archive=%{http_code}\n" https://footballpredictor.it.com/archive
curl -s -o /dev/null -w "accuracy=%{http_code}\n" https://footballpredictor.it.com/accuracy
echo SMOKE_OK
