#!/usr/bin/env bash
set -eu
cd /opt/worldcup-predictor
BACKUP=data/backups/pre_full_project_sync_2_untracked_quarantine
mkdir -p "$BACKUP"
git fetch origin main
git diff --name-only HEAD origin/main | while IFS= read -r f; do
  if [ -n "$f" ] && [ -f "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    mkdir -p "$BACKUP/$(dirname "$f")"
    mv "$f" "$BACKUP/$f"
    echo "quarantined: $f"
  fi
done
git pull --ff-only origin main
echo "HEAD=$(git rev-parse HEAD)"
echo "ORIGIN=$(git rev-parse origin/main)"
