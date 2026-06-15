# Hetzner Linux Deployment Guide

Deploy **WorldCup Predictor Pro 2026** Streamlit GUI on Ubuntu (Hetzner Cloud or dedicated).

## Overview

| Component | Path / port |
|-----------|-------------|
| Streamlit GUI | `worldcup_predictor/ui/gui_app.py` on `0.0.0.0:8501` (internal) |
| SQLite DB | `data/football_intelligence.db` |
| Backups | `backups/sqlite/` (keep latest 20) |
| Secrets | `.env.production` (never commit) |

**Security model:** expose **80/443** via Nginx; bind Streamlit to **127.0.0.1:8501** only. Enable GUI password auth with `APP_AUTH_ENABLED`.

---

## 1. Server preparation (Ubuntu 22.04+)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin nginx ufw git curl
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
# Do NOT: ufw allow 8501
```

Clone or copy the project to `/opt/worldcup-predictor`:

```bash
sudo mkdir -p /opt/worldcup-predictor
sudo chown $USER:$USER /opt/worldcup-predictor
# git clone <your-repo> /opt/worldcup-predictor
cd /opt/worldcup-predictor
```

Or run the helper script:

```bash
chmod +x scripts/deploy_hetzner.sh scripts/backup_sqlite.sh
sudo APP_DIR=/opt/worldcup-predictor REPO_URL=<your-git-url> ./scripts/deploy_hetzner.sh
```

---

## 2. Configure production secrets

```bash
cp .env.production.example .env.production
nano .env.production
```

Required:

- `API_FOOTBALL_KEY` — live fixtures
- `APP_AUTH_ENABLED=true`
- `APP_USERNAME` / `APP_PASSWORD` — GUI login

Optional: `OPENAI_API_KEY`, weather/odds keys, `DEFAULT_LOCALE` (`en|de|fa|sr|bs|hr`).

**Never commit `.env.production` or real API keys.**

---

## 3. Docker deployment (recommended)

```bash
mkdir -p data backups/sqlite reports .cache/api_football
docker compose up -d --build
docker compose logs -f
```

`docker-compose.yml` binds `127.0.0.1:8501:8501` so the GUI is not public until Nginx proxies it.

Health check: `curl -f http://127.0.0.1:8501/_stcore/health`

---

## 4. Nginx reverse proxy (HTTPS)

Install Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

Example `/etc/nginx/sites-available/worldcup-predictor`:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name predictor.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name predictor.example.com;

    ssl_certificate     /etc/letsencrypt/live/predictor.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/predictor.example.com/privkey.pem;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 86400;
    }
}
```

Enable and reload:

```bash
sudo ln -sf /etc/nginx/sites-available/worldcup-predictor /etc/nginx/sites-enabled/
sudo certbot --nginx -d predictor.example.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. SQLite backups

Manual backup:

```bash
./scripts/backup_sqlite.sh
```

Cron (daily at 03:00 UTC):

```cron
0 3 * * * /opt/worldcup-predictor/scripts/backup_sqlite.sh >> /var/log/worldcup-backup.log 2>&1
```

Keeps the **latest 20** files in `backups/sqlite/`.

---

## 6. Systemd alternative (without Docker)

Create `/etc/systemd/system/worldcup-gui.service`:

```ini
[Unit]
Description=WorldCup Predictor Streamlit GUI
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/worldcup-predictor
EnvironmentFile=/opt/worldcup-predictor/.env.production
ExecStart=/opt/worldcup-predictor/.venv/bin/streamlit run worldcup_predictor/ui/gui_app.py \
    --server.address 127.0.0.1 \
    --server.port 8501 \
    --server.enableCORS false \
    --server.enableXsrfProtection true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Setup:

```bash
cd /opt/worldcup-predictor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo chown -R www-data:www-data data backups reports .cache
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-gui
```

Use the same Nginx block pointing to `127.0.0.1:8501`.

---

## 7. GUI authentication

When `APP_AUTH_ENABLED=true`, users must sign in before accessing any page.

| Variable | Description |
|----------|-------------|
| `APP_AUTH_ENABLED` | `true` / `false` |
| `APP_USERNAME` | Login username |
| `APP_PASSWORD` | Login password |

API keys are **never** shown in the GUI or logs.

---

## 8. Languages

GUI supports: **English**, **Deutsch**, **فارسی**, **Srpski**, **Bosanski**, **Hrvatski**.

Set default: `DEFAULT_LOCALE=sr` (or `bs`, `hr`) in `.env.production`.

Missing translation keys fall back to English automatically.

---

## 9. Local verification

```bash
# Development
python main.py gui

# Docker
docker compose up --build
```

Open `http://127.0.0.1:8501` locally. On the server, use your Nginx HTTPS URL.

---

## 10. Firewall checklist

| Port | Action |
|------|--------|
| 22 | Allow (SSH) |
| 80 | Allow (HTTP → HTTPS redirect) |
| 443 | Allow (HTTPS / Nginx) |
| 8501 | **Do not expose publicly** — localhost + Nginx only |

---

## Troubleshooting

- **502 Bad Gateway:** `docker compose ps` — ensure container is healthy.
- **Login loop:** verify `APP_USERNAME` / `APP_PASSWORD` in `.env.production`.
- **No live data:** check `API_FOOTBALL_KEY` in `.env.production`, restart container.
- **WebSocket issues behind proxy:** ensure Nginx `Upgrade` / `Connection` headers (see config above).
