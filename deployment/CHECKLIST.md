# Phase 4 — Hetzner deployment checklist

Use this **before** running deploy commands on the server. Do not skip PostgreSQL or JWT steps.

## A. Local prep (developer machine)

- [ ] All Phase 3 checks pass: `python scripts/validate_phase3_auth_http.py`
- [ ] Frontend builds: `cd base44-d && npm run build`
- [ ] Production readiness audit: `python scripts/validate_production_readiness.py`
- [ ] Commit and push to remote: `git push origin main`
- [ ] Copy secrets to password manager (never commit `.env.production`)

## B. Server first boot

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx git ufw nodejs npm postgresql postgresql-contrib rsync
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

## C. Clone application

```bash
sudo mkdir -p /opt/worldcup-predictor /var/www/worldcup/frontend
sudo chown -R $USER:$USER /opt/worldcup-predictor /var/www/worldcup
cd /opt/worldcup-predictor
git clone <YOUR_REPO_URL> .
```

## D. PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE USER worldcup_user WITH PASSWORD 'CHANGE_ME_STRONG';
CREATE DATABASE worldcup_predictor OWNER worldcup_user;
GRANT ALL PRIVILEGES ON DATABASE worldcup_predictor TO worldcup_user;
SQL
```

## E. Production environment file

```bash
cp deployment/.env.production.example .env.production
nano .env.production
```

Required values:

| Variable | Required |
|----------|----------|
| `APP_ENV=production` | Yes |
| `DATABASE_URL` | Yes |
| `JWT_SECRET` (32+ chars) | Yes |
| `ADMIN_USERNAME` | Yes |
| `ADMIN_PASSWORD` (12+ chars) | Yes |
| `PUBLIC_ACCESS_CODE` | Recommended |
| `API_FOOTBALL_KEY` | Yes |
| `CORS_ALLOWED_ORIGINS` | If cross-origin |

## F. Python backend

```bash
cd /opt/worldcup-predictor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
set -a && source .env.production && set +a
alembic upgrade head
python scripts/validate_production_readiness.py --require-production-env
mkdir -p data backups/sqlite reports .cache/api_football logs
sudo chown -R www-data:www-data data backups reports .cache logs
```

## G. Systemd (FastAPI)

```bash
sudo cp deployment/systemd/worldcup-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-api
sudo journalctl -u worldcup-api -n 50 --no-pager
curl -s http://127.0.0.1:8000/api/health
```

## H. Frontend build

```bash
cd /opt/worldcup-predictor/base44-d
npm ci
npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
sudo chown -R www-data:www-data /var/www/worldcup
```

Verify `base44-d/.env.production` has **empty** `VITE_API_BASE_URL=` (same-origin `/api`).

## I. Nginx — test with IP first

```bash
sed "s/YOUR_SERVER_IP/$(curl -s ifconfig.me)/" deployment/nginx/worldcup-ip.conf | sudo tee /etc/nginx/sites-available/worldcup-ip
sudo ln -sf /etc/nginx/sites-available/worldcup-ip /etc/nginx/sites-enabled/worldcup-ip
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
curl -s http://YOUR_SERVER_IP/api/health
```

Browser: `http://YOUR_SERVER_IP` → register → login → dashboard → match center → prediction.

## J. Domain + SSL (after IP test)

```bash
sed "s/YOUR_DOMAIN/predictor.example.com/g" deployment/nginx/worldcup.conf | sudo tee /etc/nginx/sites-available/worldcup
sudo ln -sf /etc/nginx/sites-available/worldcup /etc/nginx/sites-enabled/worldcup
sudo rm -f /etc/nginx/sites-enabled/worldcup-ip
sudo nginx -t
sudo certbot --nginx -d predictor.example.com
sudo systemctl reload nginx
```

Set in `.env.production` if needed:

```
CORS_ALLOWED_ORIGINS=https://predictor.example.com
```

Restart API: `sudo systemctl restart worldcup-api`

## K. Post-deploy verification

```bash
curl -s https://predictor.example.com/api/health
curl -s "https://predictor.example.com/api/matches/upcoming?limit=3"
```

Manual browser checklist:

- [ ] Register (with invite code)
- [ ] Login / logout
- [ ] Dashboard loads real data
- [ ] Match Center fixtures
- [ ] Prediction detail runs
- [ ] Settings save
- [ ] Admin health (admin user)

## L. Redeploy (updates)

```bash
cd /opt/worldcup-predictor && git pull
source .venv/bin/activate && pip install -r requirements.txt
set -a && source .env.production && set +a
alembic upgrade head
sudo systemctl restart worldcup-api
cd base44-d && npm ci && npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
```

See `deployment/ROLLBACK.md` if something breaks.
