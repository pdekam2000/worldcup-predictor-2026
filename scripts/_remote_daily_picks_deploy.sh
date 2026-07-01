#!/bin/bash
set -euo pipefail

echo "=== GIT PULL ==="
cd /opt/worldcup-predictor
git pull

echo "=== RESTART API ==="
source .venv/bin/activate
sudo systemctl restart worldcup-api
sleep 3
systemctl is-active worldcup-api

echo "=== FRONTEND BUILD ==="
cd base44-d
npm ci
npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
sudo chown -R www-data:www-data /var/www/worldcup/frontend/dist/ 2>/dev/null || true

echo "=== NGINX RELOAD ==="
sudo nginx -t
sudo systemctl reload nginx

echo "=== SYSTEMD DAILY PICKS ==="
cd /opt/worldcup-predictor
sudo cp deployment/systemd/worldcup-daily-picks.service /etc/systemd/system/
sudo cp deployment/systemd/worldcup-daily-picks.timer /etc/systemd/system/
sudo cp deployment/systemd/worldcup-update-pick-results.service /etc/systemd/system/
sudo cp deployment/systemd/worldcup-update-pick-results.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-daily-picks.timer
sudo systemctl enable --now worldcup-update-pick-results.timer

echo "=== TIMER STATUS ==="
systemctl list-timers worldcup-daily-picks.timer worldcup-update-pick-results.timer --no-pager

echo "=== HEALTH ==="
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/daily-picks | head -c 200
echo

echo "=== DONE ==="
