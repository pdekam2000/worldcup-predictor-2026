#!/usr/bin/env bash
set -euo pipefail

REPO=/opt/worldcup-predictor
DIST_TARGET=/var/www/worldcup/frontend/dist
BACKUP="/var/www/worldcup/frontend/dist-backup-phase6-$(date +%Y%m%d-%H%M%S)"

cd "$REPO"
echo "=== git ==="
git rev-parse HEAD
git log -1 --oneline

if [ -d "$DIST_TARGET" ]; then
  cp -a "$DIST_TARGET" "$BACKUP"
  echo "Backup: $BACKUP"
else
  echo "No existing dist at $DIST_TARGET"
fi

cd "$REPO/base44-d"
npm ci
npm run build

mkdir -p "$DIST_TARGET"
rsync -a --delete dist/ "$DIST_TARGET/"
chown -R www-data:www-data "$DIST_TARGET"

echo "=== deployed assets ==="
ls -la "$DIST_TARGET" | head -10
echo "index.html bytes: $(wc -c < "$DIST_TARGET/index.html")"
