#!/usr/bin/env bash
# Phase 64 — safe production git sync with full backup.
set -euo pipefail

APP="${APP:-/opt/worldcup-predictor}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP="${APP}/backups/phase64-sync-${TS}"

echo "=== Phase 64 Production Git Sync ==="
mkdir -p "${BACKUP}"

cd "${APP}"

echo "=== 1. Backup ==="
git rev-parse HEAD > "${BACKUP}/pre_sync_commit.txt"
cp -a "${FRONTEND_DIST}" "${BACKUP}/frontend_dist" 2>/dev/null || true
cp -a .env.production "${BACKUP}/.env.production" 2>/dev/null || true
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

TARGET="${PHASE64_TARGET_REF:-origin/main}"
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse "${TARGET}")

echo "local_head=${LOCAL_HEAD}"
echo "remote_head=${REMOTE_HEAD}"

if [ "${LOCAL_HEAD}" = "${REMOTE_HEAD}" ]; then
  echo "Already at target commit"
else
  # Check for risky local modifications on critical hotfix files
  HOTFIX_FILES=(
    worldcup_predictor/api/web_auth.py
    worldcup_predictor/api/routes/auth.py
    base44-d/src/pages/Login.jsx
  )
  CONFLICT=0
  for f in "${HOTFIX_FILES[@]}"; do
    if git diff --quiet HEAD -- "$f" 2>/dev/null; then
      continue
    fi
    if git diff "${REMOTE_HEAD}" HEAD -- "$f" 2>/dev/null | grep -q .; then
      echo "WARN: local changes on $f differ from remote"
    fi
  done

  echo "=== 4. Stash local changes (keep runtime) ==="
  git stash push -u -m "phase64-pre-sync-${TS}" || true

  echo "=== 5. Checkout target ==="
  git checkout main
  git reset --hard "${REMOTE_HEAD}"
fi

echo "=== 6. Restore runtime data ==="
mkdir -p data/shadow data/enterprise
cp -a "${RUNTIME_STASH}/shadow/"*.jsonl data/shadow/ 2>/dev/null || true
cp -a "${RUNTIME_STASH}/enterprise/"*.json data/enterprise/ 2>/dev/null || true
chown -R www-data:www-data data/enterprise 2>/dev/null || true
chmod 775 data/enterprise 2>/dev/null || true

echo "=== 7. Build frontend ==="
cd "${APP}/base44-d"
npm run build
rsync -a --delete dist/ "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}"

echo "=== 8. Restart services ==="
systemctl restart worldcup-api
sleep 3
nginx -t && systemctl reload nginx

echo "=== 9. Smoke ==="
curl -sS -o /dev/null -w "health=%{http_code}\n" https://footballpredictor.it.com/api/health
curl -sS -o /dev/null -w "login=%{http_code}\n" https://footballpredictor.it.com/login

echo "sync_head=$(git -C ${APP} rev-parse HEAD)"
echo "=== DONE ==="
