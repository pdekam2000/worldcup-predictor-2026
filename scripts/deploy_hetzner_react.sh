#!/usr/bin/env bash
# Hetzner CX33 — React frontend + FastAPI (production port 8000)
# Usage: DOMAIN=predictor.example.com REPO_URL=https://github.com/you/repo.git sudo -E bash scripts/deploy_hetzner_react.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
WEB_ROOT="${WEB_ROOT:-/var/www/worldcup/frontend}"
DOMAIN="${DOMAIN:?Set DOMAIN=predictor.example.com}"
REPO_URL="${REPO_URL:-}"

echo "==> App dir: $APP_DIR"
echo "==> Domain:  $DOMAIN"

apt-get update
apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git ufw nodejs npm rsync

ufw allow 22/tcp || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw --force enable || true

mkdir -p "$APP_DIR" "$(dirname "$WEB_ROOT")"
if [[ -n "$REPO_URL" && ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdir -p data backups/sqlite reports .cache/api_football logs
if [[ ! -f .env.production ]]; then
  echo "Create $APP_DIR/.env.production from deployment/.env.production.example then re-run."
  exit 1
fi

set -a && source .env.production && set +a
alembic upgrade head

chown -R www-data:www-data data backups reports .cache || true

cp deployment/systemd/worldcup-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable worldcup-api
systemctl restart worldcup-api
curl -sf http://127.0.0.1:8000/api/health

cd base44-d
npm ci
npm run build
rsync -a dist/ "$WEB_ROOT/dist/"
chown -R www-data:www-data /var/www/worldcup

sed "s/YOUR_DOMAIN/$DOMAIN/g" deployment/nginx/worldcup.conf > /etc/nginx/sites-available/worldcup
ln -sf /etc/nginx/sites-available/worldcup /etc/nginx/sites-enabled/worldcup
rm -f /etc/nginx/sites-enabled/default
nginx -t
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" || certbot --nginx -d "$DOMAIN"
systemctl reload nginx

echo "Done. Verify: curl -s https://$DOMAIN/api/health"
