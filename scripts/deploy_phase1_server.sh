#!/usr/bin/env bash
# Deployment Phase 1 — prepare /opt/worldcup-predictor (no systemd/nginx/API switch)
set -uo pipefail

APP="/opt/worldcup-predictor"
OLD="/opt/worldcup-predictor-2026-main"
SRC="$OLD/data/football_intelligence.db"
DST="$APP/data/football_intelligence.db"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }
info() { printf 'INFO\t%s\n' "$1"; }

echo "=== Deployment Phase 1 ==="

# 1. SQLite copy
mkdir -p "$APP/data"
if [[ ! -f "$SRC" ]]; then
  fail "Source SQLite missing at $SRC"
else
  if [[ -f "$DST" ]]; then
    src_sz=$(stat -c%s "$SRC")
    dst_sz=$(stat -c%s "$DST")
    if [[ "$src_sz" -eq "$dst_sz" ]]; then
      pass "SQLite already at destination"
    else
      cp -a "$SRC" "$DST"
      pass "SQLite refreshed from old path"
    fi
  else
    cp -a "$SRC" "$DST"
    pass "SQLite copied to new path"
  fi
  info "SQLite size: $(du -h "$DST" | cut -f1)"
fi

# 2. .env.production (never overwrite existing)
if [[ -f "$APP/.env.production" ]]; then
  pass ".env.production exists — not overwritten"
else
  cp "$APP/deployment/.env.production.example" "$APP/.env.production"
  chmod 600 "$APP/.env.production"
  pass ".env.production created from example"
fi

# 3. Check if secrets still placeholders
ENV="$APP/.env.production"
needs_secrets=0
grep -q 'CHANGE_ME' "$ENV" 2>/dev/null && needs_secrets=1
grep -q 'your_api_football_key' "$ENV" 2>/dev/null && needs_secrets=1
if [[ "$needs_secrets" -eq 1 ]]; then
  fail "Secrets still placeholders — edit $ENV before alembic"
else
  pass "Secrets appear configured (no obvious placeholders)"
fi

# 4. Packages
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nodejs npm python3-venv python3-pip >/dev/null
if command -v node >/dev/null; then pass "Node: $(node -v)"; else fail "Node not installed"; fi
if command -v npm >/dev/null; then pass "npm: $(npm -v)"; else fail "npm not installed"; fi
if python3 -m venv --help >/dev/null 2>&1; then pass "python3-venv available"; else fail "python3-venv missing"; fi

# 5. Python venv
if [[ ! -d "$APP/.venv" ]]; then
  python3 -m venv "$APP/.venv"
  pass "Created .venv"
else
  pass ".venv already exists"
fi
# shellcheck disable=SC1091
source "$APP/.venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$APP/requirements.txt"
pass "Python dependencies installed"

# 6. Alembic (only if secrets configured)
if [[ "$needs_secrets" -eq 0 ]]; then
  cd "$APP"
  set -a
  # shellcheck disable=SC1091
  source "$ENV"
  set +a
  if alembic upgrade head; then
    pass "alembic upgrade head completed"
  else
    fail "alembic upgrade head failed"
  fi
else
  info "Skipping alembic — waiting for manual secret fill"
fi

echo "=== Phase 1 complete ==="
