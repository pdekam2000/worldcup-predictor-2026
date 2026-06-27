#!/usr/bin/env bash
set -eu
APP=/opt/worldcup-predictor
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="$APP/backups/hotfix-h4-$TS"
mkdir -p "$BACKUP"
cp -a /var/www/worldcup/frontend/dist "$BACKUP/frontend_dist" 2>/dev/null || true
cp -a "$APP/worldcup_predictor/api/display_helpers.py" "$BACKUP/" 2>/dev/null || true
git -C "$APP" rev-parse HEAD > "$BACKUP/commit.txt" 2>/dev/null || true

tar xzf /tmp/hotfix_h4_deploy.tar.gz -C "$APP"
if [ -d /tmp/hotfix_h4_dist ]; then
  rsync -a --delete /tmp/hotfix_h4_dist/ /var/www/worldcup/frontend/dist/
  chown -R www-data:www-data /var/www/worldcup/frontend/dist/ 2>/dev/null || true
fi

systemctl restart worldcup-api
sleep 6
systemctl is-active worldcup-api

cd "$APP"
H4_API_BASE=http://127.0.0.1:8000 .venv/bin/python scripts/validate_hotfix_h4_live_debug.py | tee "$BACKUP/validate.log"

BEFORE=$(curl -s "http://127.0.0.1:8000/api/matches?competition=world_cup_2026&include_summary=true&page_size=5" | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(1 for r in d.get('matches',[]) if r.get('home_team_logo')))")
echo "logos_in_top5=$BEFORE"

curl -s -o /dev/null -w "health=%{http_code}\n" https://footballpredictor.it.com/api/health
curl -s -o /dev/null -w "matches=%{http_code}\n" https://footballpredictor.it.com/matches
curl -s -o /dev/null -w "detail1489409=%{http_code}\n" "https://footballpredictor.it.com/matches/1489409?competition=league_1"
curl -s -o /dev/null -w "detail1489410=%{http_code}\n" "https://footballpredictor.it.com/matches/1489410?competition=world_cup_2026"
curl -s -o /dev/null -w "elite_shadow=%{http_code}\n" https://footballpredictor.it.com/admin/elite-shadow
echo DEPLOY_OK
