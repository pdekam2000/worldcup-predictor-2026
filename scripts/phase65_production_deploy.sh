#!/usr/bin/env bash
# Phase 65 — production deploy with backup + autonomous readiness runs.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase65-deploy-${TS}"

echo "=== Phase 65 Production Deploy ==="
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Full backup ==="
git rev-parse HEAD > "${BACKUP}/pre_deploy_commit.txt"
cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
cp -a .env.production "${BACKUP}/.env.production" 2>/dev/null || true
cp -a .env "${BACKUP}/.env" 2>/dev/null || true
if [ -f data/football_intelligence.db ]; then
  cp -a data/football_intelligence.db "${BACKUP}/football_intelligence.db"
fi
mkdir -p "${BACKUP}/runtime"
cp -a data/shadow/*.jsonl "${BACKUP}/runtime/" 2>/dev/null || true
cp -a data/enterprise/*.json "${BACKUP}/runtime/" 2>/dev/null || true

if command -v pg_dump >/dev/null 2>&1 && [ -f .env.production ]; then
  set -a && source .env.production && set +a
  if [ -n "${DATABASE_URL:-}" ]; then
    pg_dump "${DATABASE_URL}" > "${BACKUP}/postgres_dump.sql" 2>/dev/null || echo "pg_dump skipped"
  fi
fi

echo "=== 2. Preserve runtime data ==="
RUNTIME_STASH="${BACKUP}/stash"
mkdir -p "${RUNTIME_STASH}/shadow" "${RUNTIME_STASH}/enterprise"
cp -a data/shadow/*.jsonl "${RUNTIME_STASH}/shadow/" 2>/dev/null || true
cp -a data/enterprise/*.json "${RUNTIME_STASH}/enterprise/" 2>/dev/null || true

echo "=== 3. Fetch origin ==="
git fetch origin
TARGET="${PHASE65_TARGET_REF:-origin/main}"
git stash push -u -m "phase65-pre-deploy-${TS}" || true
git checkout main
git reset --hard "${TARGET}"

echo "=== 4. Restore runtime ==="
mkdir -p data/shadow data/enterprise
cp -a "${RUNTIME_STASH}/shadow/"*.jsonl data/shadow/ 2>/dev/null || true
cp -a "${RUNTIME_STASH}/enterprise/"*.json data/enterprise/ 2>/dev/null || true
chown -R www-data:www-data data/enterprise 2>/dev/null || true

echo "=== 5. Build frontend ==="
cd "${APP}/base44-d"
npm run build
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}"

echo "=== 6. Restart services ==="
systemctl restart worldcup-api
sleep 3
nginx -t && systemctl reload nginx

echo "=== 7. Autonomous runs (2x cache-first, limit 10) ==="
for i in 1 2; do
  echo "--- autonomous run ${i}/2 ---"
  sudo -u www-data "${APP}/.venv/bin/python" - <<'PY'
import json
from worldcup_predictor.owner.platform_service import OwnerPlatformService
svc = OwnerPlatformService()
result = svc.run_once(fixture_limit=10, dry_run=False)
print(json.dumps({
    "status": result.get("report", {}).get("status"),
    "streak": result.get("autonomous", {}).get("consecutive_successes"),
    "api_calls": result.get("report", {}).get("api_calls_used"),
    "readiness": result.get("autonomous", {}).get("scheduler_readiness", {}).get("scheduler_status"),
}, indent=2))
PY
done

echo "=== 8. Validation ==="
cd "${APP}"
"${APP}/.venv/bin/python" scripts/validate_phase65_elite_promotion_betting_intelligence.py || true

echo "=== 9. Smoke ==="
for path in \
  /api/health \
  /login \
  /owner \
  /owner/model-center \
  /owner/research-lab \
  /owner/promotion-center \
  /owner/betting-intelligence \
  /owner/autonomous; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com${path}")
  echo "${path}=${code}"
done

echo "deploy_head=$(git -C ${APP} rev-parse HEAD)"
echo "=== DONE ==="
