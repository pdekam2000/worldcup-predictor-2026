#!/usr/bin/env bash
# Read-only Hetzner pre-flight — no deploy, no secrets printed.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-predictor}"
ALT_DIR="/opt/worldcup-predictor-2026-main"
WEB_ROOT="${WEB_ROOT:-/var/www/worldcup/frontend/dist}"
BACKUP_DIR="${BACKUP_DIR:-/opt/worldcup-predictor/backups/preflight_$(date -u +%Y%m%d_%H%M%S)}"

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; }
skip() { printf 'SKIP: %s\n' "$1"; }
info() { printf 'INFO: %s\n' "$1"; }

mask_set() {
  local key="$1" file="$2"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    local val
    val="$(grep "^${key}=" "$file" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
    if [[ -n "$val" && "$val" != "CHANGE_ME"* && "$val" != "your_"* ]]; then
      echo "set (${#val} chars)"
    else
      echo "missing or placeholder"
    fi
  else
    echo "not in file"
  fi
}

echo "=== Hetzner Server Pre-Flight ==="
echo "Host: $(hostname) | IP: $(hostname -I 2>/dev/null | awk '{print $1}')"
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# 1. App path
if [[ -d "$APP_DIR" ]]; then
  pass "App directory $APP_DIR exists"
  WORK_DIR="$APP_DIR"
elif [[ -d "$ALT_DIR" ]]; then
  fail "Expected $APP_DIR — found $ALT_DIR instead (rename or symlink before deploy)"
  WORK_DIR="$ALT_DIR"
else
  fail "No app at $APP_DIR or $ALT_DIR"
  WORK_DIR=""
fi

if [[ -n "$WORK_DIR" ]]; then
  info "Working tree: $WORK_DIR"
  if [[ -d "$WORK_DIR/.git" ]]; then
    pass "Git repo present"
    info "Branch: $(git -C "$WORK_DIR" branch --show-current 2>/dev/null || echo '?')"
    info "HEAD: $(git -C "$WORK_DIR" log -1 --oneline 2>/dev/null || echo '?')"
    if git -C "$WORK_DIR" remote get-url origin &>/dev/null; then
      info "Remote: $(git -C "$WORK_DIR" remote get-url origin)"
    fi
    if git -C "$WORK_DIR" status --porcelain 2>/dev/null | grep -q .; then
      fail "Server working tree has uncommitted changes"
    else
      pass "Server working tree clean"
    fi
  else
    fail "Not a git clone — zip extract only? Use git clone for deploy"
  fi

  if [[ -f "$WORK_DIR/deployment/systemd/worldcup-api.service" ]]; then
    pass "systemd unit template present"
  else
    fail "deployment/systemd/worldcup-api.service missing (old codebase?)"
  fi
  if [[ -f "$WORK_DIR/deployment/nginx/worldcup-ip.conf" ]]; then
    pass "nginx IP config template present"
  else
    fail "deployment/nginx/worldcup-ip.conf missing (Phase 4 artifacts?)"
  fi
  if [[ -f "$WORK_DIR/alembic.ini" ]]; then
    pass "alembic.ini present"
  else
    fail "alembic.ini missing (PostgreSQL SaaS migrations not on server)"
  fi
fi

# 2. Backups (report only — do not overwrite)
mkdir -p "$BACKUP_DIR" 2>/dev/null || true
info "Backup staging: $BACKUP_DIR"

for envf in "$APP_DIR/.env.production" "$ALT_DIR/.env.production" "$APP_DIR/.env" "$ALT_DIR/.env"; do
  if [[ -f "$envf" ]]; then
    pass ".env exists: $envf"
    cp -a "$envf" "$BACKUP_DIR/$(basename "$(dirname "$envf")")_$(basename "$envf").bak" 2>/dev/null || true
    info "  backed up to $BACKUP_DIR (not printed)"
  fi
done

for db in "$APP_DIR/data/football_intelligence.db" "$ALT_DIR/data/football_intelligence.db"; do
  if [[ -f "$db" ]]; then
    sz=$(du -h "$db" | cut -f1)
    pass "SQLite intelligence DB exists: $db ($sz)"
    cp -a "$db" "$BACKUP_DIR/football_intelligence.db.bak" 2>/dev/null || true
  fi
done

# 3. Production env (masked)
ENV_FILE=""
for f in "$APP_DIR/.env.production" "$ALT_DIR/.env.production"; do
  [[ -f "$f" ]] && ENV_FILE="$f" && break
done
if [[ -n "$ENV_FILE" ]]; then
  pass ".env.production found: $ENV_FILE"
  for key in APP_ENV DATABASE_URL JWT_SECRET ADMIN_USERNAME ADMIN_PASSWORD PUBLIC_ACCESS_CODE API_FOOTBALL_KEY SPORTMONKS_API_TOKEN; do
    info "  $key = $(mask_set "$key" "$ENV_FILE")"
  done
  if grep -q '^APP_ENV=production' "$ENV_FILE"; then pass "APP_ENV=production"; else fail "APP_ENV not production"; fi
  if grep -q '^DATABASE_URL=postgresql' "$ENV_FILE"; then pass "DATABASE_URL is postgresql"; else fail "DATABASE_URL not postgresql"; fi
else
  fail ".env.production not found"
fi

# 4. PostgreSQL
if systemctl is-active --quiet postgresql 2>/dev/null; then
  pass "PostgreSQL service active"
else
  fail "PostgreSQL service not active"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='worldcup_user'" 2>/dev/null | grep -q 1; then
  pass "PostgreSQL role worldcup_user exists"
else
  fail "PostgreSQL role worldcup_user missing"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='worldcup_predictor'" 2>/dev/null | grep -q 1; then
  pass "PostgreSQL database worldcup_predictor exists"
  tbl_count=$(sudo -u postgres psql -d worldcup_predictor -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo 0)
  info "  public tables: $tbl_count"
else
  fail "PostgreSQL database worldcup_predictor missing"
fi

# 5. Backend systemd
if systemctl list-unit-files worldcup-api.service &>/dev/null; then
  state=$(systemctl is-active worldcup-api 2>/dev/null || echo inactive)
  if [[ "$state" == "active" ]]; then
    pass "worldcup-api.service active"
  else
    skip "worldcup-api.service installed but $state"
  fi
else
  skip "worldcup-api.service not installed"
fi

if curl -sf http://127.0.0.1:8000/api/health &>/dev/null; then
  pass "FastAPI health on 127.0.0.1:8000"
else
  fail "No API health on 127.0.0.1:8000"
fi

# 6. Frontend
if [[ -d "$WEB_ROOT" && -f "$WEB_ROOT/index.html" ]]; then
  pass "Frontend dist at $WEB_ROOT"
else
  fail "Frontend dist missing at $WEB_ROOT"
fi

if [[ -n "$WORK_DIR" && -d "$WORK_DIR/base44-d" ]]; then
  if [[ -d "$WORK_DIR/base44-d/dist" ]]; then
    pass "base44-d/dist built in repo"
  else
    fail "base44-d/dist not built on server"
  fi
fi

# 7. Nginx
if systemctl is-active --quiet nginx 2>/dev/null; then
  pass "nginx active"
else
  fail "nginx not active"
fi

if nginx -t &>/dev/null; then
  pass "nginx config syntax OK"
else
  fail "nginx -t failed"
fi

if grep -r "proxy_pass.*127.0.0.1:8000/api" /etc/nginx/sites-enabled/ &>/dev/null; then
  pass "nginx proxies /api to :8000"
else
  fail "nginx /api proxy to :8000 not found in sites-enabled"
fi

pub_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
if curl -sf "http://${pub_ip}/api/health" &>/dev/null; then
  pass "Public IP /api/health (${pub_ip})"
else
  skip "Public IP /api/health not reachable (firewall or no site for IP)"
fi

echo
echo "=== Pre-flight complete (no deploy performed) ==="
echo "Backup copies (if any): $BACKUP_DIR"
