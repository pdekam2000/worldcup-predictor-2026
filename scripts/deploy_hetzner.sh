#!/usr/bin/env bash
# Quick Hetzner Ubuntu deployment helper for WorldCup Predictor Pro GUI.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
REPO_URL="${REPO_URL:-}"

echo "==> WorldCup Predictor — Hetzner deploy helper"
echo "Target directory: ${APP_DIR}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root or with sudo for package install / systemd steps."
fi

apt-get update
apt-get install -y docker.io docker-compose-plugin nginx ufw curl git

if [[ ! -d "${APP_DIR}" ]]; then
  mkdir -p "${APP_DIR}"
fi

if [[ -n "${REPO_URL}" ]]; then
  if [[ ! -d "${APP_DIR}/.git" ]]; then
    git clone "${REPO_URL}" "${APP_DIR}"
  else
    git -C "${APP_DIR}" pull --ff-only
  fi
else
  echo "Copy project files into ${APP_DIR} (or set REPO_URL=...)"
fi

cd "${APP_DIR}"

if [[ ! -f .env.production ]]; then
  cp .env.production.example .env.production
  echo "Created .env.production — edit secrets before starting!"
fi

mkdir -p data backups/sqlite reports .cache/api_football
chmod +x scripts/backup_sqlite.sh scripts/deploy_hetzner.sh 2>/dev/null || true

# Firewall — SSH + HTTP/S only; do NOT expose 8501 publicly
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable || true

docker compose up -d --build

echo ""
echo "Deploy complete."
echo "1. Edit ${APP_DIR}/.env.production with real API keys and APP_PASSWORD"
echo "2. Configure Nginx reverse proxy (see docs/HETZNER_DEPLOYMENT.md)"
echo "3. Schedule backups: crontab -e"
echo "   0 3 * * * ${APP_DIR}/scripts/backup_sqlite.sh >> /var/log/worldcup-backup.log 2>&1"
echo "4. GUI listens on 127.0.0.1:8501 inside Docker — access via Nginx HTTPS"
