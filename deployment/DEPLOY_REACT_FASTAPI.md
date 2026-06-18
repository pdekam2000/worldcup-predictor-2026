# React + FastAPI deployment (Hetzner CX33)

Production stack: **Nginx** (static React + `/api` proxy) → **uvicorn :8000** → **PostgreSQL** (SaaS) + **SQLite** (prediction intelligence).

Phase 4 artifacts: `deployment/CHECKLIST.md`, `deployment/ROLLBACK.md`, `deployment/.env.production.example`.

## Local development (port 8001)

Windows may have stale listeners on :8000 — use **8001** locally:

```bash
python scripts/local_postgres.py --hold
python -m uvicorn worldcup_predictor.api.main:app --host 127.0.0.1 --port 8001
cd base44-d && npm run dev
python scripts/validate_phase3_auth_http.py
```

Production server uses **uvicorn :8000** + Nginx `/api/` proxy.

## Architecture

| Layer | Path / port | Role |
|-------|-------------|------|
| Nginx :443 | `/var/www/worldcup/frontend/dist` | React SPA + `/api/` → FastAPI |
| uvicorn :8000 | `127.0.0.1` only | `worldcup_predictor.api.main:app` |
| PostgreSQL | `DATABASE_URL` | Users, auth, SaaS tables (Alembic) |
| SQLite | `data/football_intelligence.db` | Prediction engine intelligence (unchanged) |

## Pre-deploy audit (local)

```bash
python scripts/validate_production_readiness.py
python scripts/validate_phase3_auth_http.py
cd base44-d && npm run build
```

## Server paths

| Item | Path |
|------|------|
| App root | `/opt/worldcup-predictor` |
| Python venv | `/opt/worldcup-predictor/.venv` |
| Production env | `/opt/worldcup-predictor/.env.production` |
| Frontend build output | `/var/www/worldcup/frontend/dist` |
| API logs | `journalctl -u worldcup-api` |
| Nginx logs | `/var/log/nginx/` |

## Quick deploy commands

See **`deployment/CHECKLIST.md`** for the full step-by-step list. Summary:

```bash
# On server after clone
cp deployment/.env.production.example .env.production && nano .env.production
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
set -a && source .env.production && set +a
alembic upgrade head
sudo cp deployment/systemd/worldcup-api.service /etc/systemd/system/
sudo systemctl enable --now worldcup-api
cd base44-d && npm ci && npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
# IP test first: deployment/nginx/worldcup-ip.conf
# Then domain + SSL: deployment/nginx/worldcup.conf
```

## Production environment (required)

| Variable | Purpose |
|----------|---------|
| `APP_ENV=production` | Enables production guard on API startup |
| `DATABASE_URL` | PostgreSQL — required |
| `JWT_SECRET` | 32+ char unique secret — required |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Admin bootstrap — required |
| `PUBLIC_ACCESS_CODE` | Registration invite gate — recommended |
| `API_FOOTBALL_KEY` | Match Center + predictions — required |
| `CORS_ALLOWED_ORIGINS` | Public HTTPS origin(s) if cross-origin |
| `VITE_API_BASE_URL` | **Empty** in `base44-d/.env.production` (same-origin) |

Optional: `SPORTMONKS_API_TOKEN`, `OPENAI_API_KEY`, RapidAPI keys.

## Security notes

- API binds `127.0.0.1:8000` only — not public.
- `APP_ENV=production` blocks dev JWT placeholders and missing admin password.
- Localhost CORS origins are **not** added in production.
- No `@base44/sdk` — React talks to FastAPI only.
- Never commit `.env.production` with real secrets.

## Rollback

See `deployment/ROLLBACK.md`.
