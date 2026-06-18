# Rollback notes — WorldCup Predictor (React + FastAPI)

## Quick rollback (last good release)

```bash
cd /opt/worldcup-predictor
git log --oneline -5
git checkout <LAST_GOOD_COMMIT>
source .venv/bin/activate
pip install -r requirements.txt
set -a && source .env.production && set +a
alembic upgrade head   # only if migrations are backward-compatible
sudo systemctl restart worldcup-api
cd base44-d && npm ci && npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
```

## Stop serving (maintenance)

```bash
sudo systemctl stop worldcup-api
sudo systemctl stop nginx
```

## API-only rollback (keep frontend)

```bash
sudo systemctl stop worldcup-api
cd /opt/worldcup-predictor && git checkout <LAST_GOOD_COMMIT> -- worldcup_predictor/
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl start worldcup-api
```

## Frontend-only rollback

```bash
cd /opt/worldcup-predictor
git checkout <LAST_GOOD_COMMIT> -- base44-d/
cd base44-d && npm ci && npm run build
sudo rsync -a dist/ /var/www/worldcup/frontend/dist/
```

## Database rollback

Alembic migrations are **forward-only** in production. To undo schema changes:

1. Restore PostgreSQL from backup taken before deploy.
2. Or write a manual down-migration (not automated today).

**Before each deploy:**

```bash
pg_dump -Fc -U worldcup_user worldcup_predictor > backups/pg_$(date +%Y%m%d_%H%M).dump
```

## Logs

```bash
sudo journalctl -u worldcup-api -f
sudo tail -f /var/log/nginx/error.log
```

## Known safe fallbacks

- Prediction engine uses local SQLite (`data/football_intelligence.db`) — keep this file backed up.
- SaaS auth/users require PostgreSQL — API will not start with `APP_ENV=production` if `DATABASE_URL` or `JWT_SECRET` are invalid.
