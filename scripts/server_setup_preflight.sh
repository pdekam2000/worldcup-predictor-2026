#!/usr/bin/env bash
# Server setup pre-flight — clone repo, verify toolchain, report gaps.
# Does NOT: alembic, systemd, nginx changes, frontend deploy, overwrite .env or DB.
set -uo pipefail

REPO_URL="${REPO_URL:-https://github.com/pdekam2000/worldcup-predictor-2026.git}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-b13fb87}"
APP_DIR="/opt/worldcup-predictor"
OLD_ZIP="/opt/worldcup-predictor-2026-main"
WEB_ROOT="/var/www/worldcup/frontend/dist"
ENV_FILE="$APP_DIR/.env.production"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }
info() { printf 'INFO\t%s\n' "$1"; }

echo "=== Server Setup Pre-Flight ==="
echo "Host: $(hostname) | $(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Expected commit: $EXPECTED_COMMIT"
echo

# 1. /opt contents
info "/opt listing:"
ls -la /opt 2>/dev/null | sed 's/^/  /' || fail "Cannot list /opt"

if [[ -d "$OLD_ZIP" ]]; then
  pass "Old zip folder preserved at $OLD_ZIP"
else
  info "Old zip folder not found at $OLD_ZIP (may already be moved)"
fi

# 2. Clone fresh repo (skip destructive actions on non-git APP_DIR)
if [[ -d "$APP_DIR/.git" ]]; then
  info "Git repo already at $APP_DIR"
  cd "$APP_DIR"
  git fetch origin main --quiet 2>/dev/null || git fetch origin --quiet 2>/dev/null || true
  git checkout main 2>/dev/null || true
  git pull origin main --ff-only 2>/dev/null || true
elif [[ -d "$APP_DIR" ]]; then
  fail "$APP_DIR exists but is not a git repo — left untouched for manual review"
  WORK_DIR="$APP_DIR"
else
  if ! command -v git >/dev/null 2>&1; then
    fail "git not installed — apt install git"
  else
    info "Cloning $REPO_URL -> $APP_DIR"
    git clone "$REPO_URL" "$APP_DIR" || fail "git clone failed"
    cd "$APP_DIR" 2>/dev/null || true
  fi
fi

if [[ -d "$APP_DIR/.git" ]]; then
  WORK_DIR="$APP_DIR"
  HEAD_SHORT="$(git rev-parse --short HEAD)"
  HEAD_FULL="$(git rev-parse HEAD)"
  if [[ "$HEAD_SHORT" == "$EXPECTED_COMMIT" ]] || [[ "$HEAD_FULL" == "$EXPECTED_COMMIT"* ]]; then
    pass "Server at commit $HEAD_SHORT (matches $EXPECTED_COMMIT)"
  else
    fail "Server at $HEAD_SHORT — expected $EXPECTED_COMMIT"
  fi

  if [[ -f "$APP_DIR/deployment/systemd/worldcup-api.service" && -f "$APP_DIR/alembic.ini" ]]; then
    pass "Phase 4 SaaS artifacts present in clone"
  else
    fail "SaaS deployment artifacts missing in clone"
  fi
fi

# 3. PostgreSQL
if systemctl is-active --quiet postgresql 2>/dev/null; then
  pass "PostgreSQL service running"
else
  fail "PostgreSQL service not running"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='worldcup_user'" 2>/dev/null | grep -q 1; then
  pass "PostgreSQL user worldcup_user exists"
else
  fail "PostgreSQL user worldcup_user missing"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='worldcup_predictor'" 2>/dev/null | grep -q 1; then
  pass "PostgreSQL database worldcup_predictor exists"
else
  fail "PostgreSQL database worldcup_predictor missing"
fi

# 4. .env.production (existence only — do not create or overwrite)
if [[ -f "$ENV_FILE" ]]; then
  pass ".env.production exists at $ENV_FILE"
elif [[ -f "$OLD_ZIP/.env.production" ]]; then
  info ".env.production found only in old zip path (copy manually before deploy)"
  fail ".env.production missing at $APP_DIR"
else
  fail ".env.production missing at $APP_DIR"
fi

# 5. Node/npm
if command -v node >/dev/null 2>&1; then
  pass "Node installed: $(node -v)"
else
  fail "Node not installed"
fi
if command -v npm >/dev/null 2>&1; then
  pass "npm installed: $(npm -v)"
else
  fail "npm not installed"
fi

# 6. Python
if command -v python3 >/dev/null 2>&1; then
  pass "Python3: $(python3 --version 2>&1)"
else
  fail "python3 not installed"
fi

# 7. Nginx
if command -v nginx >/dev/null 2>&1; then
  pass "Nginx installed: $(nginx -v 2>&1)"
else
  fail "Nginx not installed"
fi

# 8. Port 8000
if ss -tlnp 2>/dev/null | grep -q ':8000 '; then
  fail "Port 8000 is in use"
  ss -tlnp 2>/dev/null | grep ':8000 ' | sed 's/^/  /' || true
else
  pass "Port 8000 is free"
fi

# 9. Frontend dist path
if [[ -d "$WEB_ROOT" && -f "$WEB_ROOT/index.html" ]]; then
  pass "Frontend dist exists at $WEB_ROOT"
else
  fail "Frontend dist missing at $WEB_ROOT"
fi

# 10. SQLite intelligence DB (for later scp — report only)
for db in "$APP_DIR/data/football_intelligence.db" "$OLD_ZIP/data/football_intelligence.db"; do
  if [[ -f "$db" ]]; then
    pass "SQLite intelligence DB found: $db ($(du -h "$db" | cut -f1))"
  fi
done
if [[ ! -f "$APP_DIR/data/football_intelligence.db" ]]; then
  fail "SQLite DB not at $APP_DIR/data/football_intelligence.db (scp from dev machine)"
fi

# 11. Python venv (report only)
if [[ -d "$APP_DIR/.venv" ]]; then
  pass "Python venv exists at $APP_DIR/.venv"
else
  fail "Python venv missing at $APP_DIR/.venv"
fi

echo
echo "=== Setup pre-flight complete (no deploy) ==="
