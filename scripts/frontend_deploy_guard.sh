#!/usr/bin/env bash
# Phase 64B — frontend deploy guard (build → lint → smoke → sync with rollback backup)
set -euo pipefail

APP="${DEPLOY_APP:-/opt/worldcup-predictor}"
FRONTEND_SRC="${FRONTEND_SRC:-${APP}/base44-d}"
FRONTEND_DIST="${FRONTEND_DIST:-/var/www/worldcup/frontend/dist}"
TS=$(date -u +%Y%m%d-%H%M%S)
BACKUP_ROOT="${APP}/backups/frontend-deploy-${TS}"
REPORT="${BACKUP_ROOT}/deploy_guard_report.txt"
FAIL=0

log() { echo "$1" | tee -a "${REPORT}"; }
pass() { log "PASS: $1"; }
fail() { log "FAIL: $1"; FAIL=1; }

mkdir -p "${BACKUP_ROOT}"

log "=== Phase 64B Frontend Deploy Guard ==="
log "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Source: ${FRONTEND_SRC}"
log "Target: ${FRONTEND_DIST}"
log "Backup: ${BACKUP_ROOT}"

# --- Part D: pre-deploy backup ---
if [ -d "${FRONTEND_DIST}" ]; then
  cp -a "${FRONTEND_DIST}" "${BACKUP_ROOT}/dist_snapshot"
  if [ -f "${FRONTEND_DIST}/index.html" ]; then
    cp -a "${FRONTEND_DIST}/index.html" "${BACKUP_ROOT}/index.html.pre"
    grep -oE '/assets/index-[^"]+\.(js|css)' "${FRONTEND_DIST}/index.html" > "${BACKUP_ROOT}/asset_hashes.pre.txt" 2>/dev/null || true
  fi
  pass "Backed up current dist → ${BACKUP_ROOT}/dist_snapshot"
else
  log "INFO: no existing dist at ${FRONTEND_DIST}"
fi

cd "${FRONTEND_SRC}"

# --- Step 1: build ---
log ""
log "--- Step 1: npm run build ---"
if npm run build 2>&1 | tee "${BACKUP_ROOT}/build.log" | tail -5; then
  pass "npm run build"
else
  fail "npm run build"
  log "DEPLOY_BLOCKED — keeping previous dist"
  log "Rollback: cp -a ${BACKUP_ROOT}/dist_snapshot/. ${FRONTEND_DIST}/"
  exit 1
fi

# --- Step 2: static import guard ---
log ""
log "--- Step 2: static import guard ---"
if node "${APP}/scripts/validate_frontend_static_imports.mjs" 2>&1 | tee "${BACKUP_ROOT}/static_imports.log" | tail -20; then
  pass "validate_frontend_static_imports"
else
  fail "validate_frontend_static_imports"
fi

# --- Step 3: smoke render ---
log ""
log "--- Step 3: smoke render ---"
if node "${APP}/scripts/validate_frontend_smoke_render.mjs" 2>&1 | tee "${BACKUP_ROOT}/smoke_render.log" | tail -25; then
  pass "validate_frontend_smoke_render"
else
  fail "validate_frontend_smoke_render"
fi

if [ "${FAIL}" -ne 0 ]; then
  log ""
  log "DEPLOY_BLOCKED — checks failed; previous dist unchanged"
  log "Rollback (if partial sync occurred): cp -a ${BACKUP_ROOT}/dist_snapshot/. ${FRONTEND_DIST}/ && systemctl reload nginx"
  exit 1
fi

# --- Step 4: sync dist ---
log ""
log "--- Step 4: sync dist ---"
mkdir -p "${FRONTEND_DIST}"
rsync -a --delete "${FRONTEND_SRC}/dist/" "${FRONTEND_DIST}/"
chown -R www-data:www-data "${FRONTEND_DIST}" 2>/dev/null || true
grep -oE '/assets/index-[^"]+\.(js|css)' "${FRONTEND_DIST}/index.html" > "${BACKUP_ROOT}/asset_hashes.post.txt" 2>/dev/null || true
pass "Synced dist to ${FRONTEND_DIST}"

# --- Step 5: reload nginx ---
if command -v nginx >/dev/null 2>&1; then
  nginx -t 2>&1 | tee -a "${REPORT}"
  systemctl reload nginx 2>/dev/null || true
  pass "nginx reload"
fi

log ""
log "DEPLOY_GUARD_OK"
log "Rollback one-liner:"
log "  cp -a ${BACKUP_ROOT}/dist_snapshot/. ${FRONTEND_DIST}/ && systemctl reload nginx"
log "BACKUP_PATH=${BACKUP_ROOT}"
