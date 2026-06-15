#!/usr/bin/env bash
# Rotate SQLite backup — keep latest 20 files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${ROOT}/data/football_intelligence.db"
BACKUP_DIR="${ROOT}/backups/sqlite"
KEEP="${KEEP_BACKUPS:-20}"

mkdir -p "${BACKUP_DIR}"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "Database not found: ${DB_PATH} (nothing to back up)"
  exit 0
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
DEST="${BACKUP_DIR}/football_intelligence_${STAMP}.db"

cp "${DB_PATH}" "${DEST}"
echo "Backup created: ${DEST}"

mapfile -t FILES < <(ls -1t "${BACKUP_DIR}"/football_intelligence_*.db 2>/dev/null || true)
if ((${#FILES[@]} > KEEP)); then
  for old in "${FILES[@]:KEEP}"; do
    rm -f "${old}"
    echo "Removed old backup: ${old}"
  done
fi

echo "Keeping latest ${KEEP} backup(s) in ${BACKUP_DIR}"
