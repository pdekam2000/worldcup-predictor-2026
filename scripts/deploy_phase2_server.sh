#!/usr/bin/env bash
# Deployment Phase 2 — switch to new SaaS stack with rollback on failure.
set -uo pipefail

APP="/opt/worldcup-predictor"
OLD="/opt/worldcup-predictor-2026-main"
WEB="/var/www/worldcup/frontend/dist"
IP="91.107.188.229"
UNIT="/etc/systemd/system/worldcup-api.service"
UNIT_BAK="/etc/systemd/system/worldcup-api.service.bak.old-stack"
NGINX_AVAIL="/etc/nginx/sites-available/worldcup-ip"
NGINX_ENABLED="/etc/nginx/sites-enabled/worldcup-ip"
NGINX_BAK="/etc/nginx/sites-available/worldcup-ip.bak.pre-phase2"
ROLLBACK=0

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }
info() { printf 'INFO\t%s\n' "$1"; }

rollback_old_api() {
  info "ROLLBACK: restoring old API stack"
  systemctl stop worldcup-api 2>/dev/null || true
  if [[ -f "$UNIT_BAK" ]]; then
    cp -a "$UNIT_BAK" "$UNIT"
    systemctl daemon-reload
    systemctl enable --now worldcup-api || true
    sleep 3
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      pass "Rollback: old API health OK"
    else
      fail "Rollback: old API still not healthy — check journalctl"
    fi
  else
    fail "Rollback: no systemd backup at $UNIT_BAK"
  fi
}

echo "=== Deployment Phase 2 ==="

# --- 1. Frontend build ---
info "Step 1: frontend build"
mkdir -p "$(dirname "$WEB")"
mkdir -p "$APP/base44-d"
if [[ ! -f "$APP/base44-d/.env.production" ]]; then
  printf '%s\n' 'VITE_API_BASE_URL=' > "$APP/base44-d/.env.production"
  pass "Created base44-d/.env.production (same-origin API)"
fi
cd "$APP/base44-d"
if npm ci && npm run build; then
  pass "npm ci && npm run build"
else
  fail "Frontend build failed"
  exit 1
fi
mkdir -p "$WEB"
rsync -a --delete dist/ "$WEB/"
if [[ -f "$WEB/index.html" ]]; then
  pass "Frontend synced to $WEB"
else
  fail "Frontend index.html missing after rsync"
  exit 1
fi

# --- Permissions for www-data API ---
info "Setting permissions for www-data"
mkdir -p "$APP/data" "$APP/.cache/api_football" "$APP/logs" "$APP/backups"
chgrp www-data "$APP/.env.production" 2>/dev/null || true
chmod 640 "$APP/.env.production" 2>/dev/null || true
chown -R www-data:www-data "$APP/data" "$APP/.cache" "$APP/logs" "$APP/backups" 2>/dev/null || true
chmod -R u+rwX,g+rwX "$APP/data" "$APP/.cache" 2>/dev/null || true

# --- 2. Stop old API ---
info "Step 2: stop old API"
if [[ -f "$UNIT" ]]; then
  cp -a "$UNIT" "$UNIT_BAK"
  pass "Backed up systemd unit to $UNIT_BAK"
fi
systemctl stop worldcup-api 2>/dev/null || true
sleep 2
if ss -tlnp 2>/dev/null | grep -q ':8000 '; then
  info "Killing processes on port 8000"
  fuser -k 8000/tcp 2>/dev/null || true
  sleep 2
fi
if ss -tlnp 2>/dev/null | grep -q ':8000 '; then
  fail "Port 8000 still in use after stop"
  rollback_old_api
  exit 1
else
  pass "Port 8000 free"
fi

# --- 3. Install new systemd ---
info "Step 3: install new systemd unit"
cp "$APP/deployment/systemd/worldcup-api.service" "$UNIT"
systemctl daemon-reload
pass "New systemd unit installed"

# --- 4. Start new API ---
info "Step 4: start new API"
systemctl enable worldcup-api
if ! systemctl restart worldcup-api; then
  fail "systemctl restart worldcup-api failed"
  journalctl -u worldcup-api -n 30 --no-pager 2>&1 | sed -E 's/(password|secret|key|token)=[^ ]+/REDACTED/gi'
  rollback_old_api
  exit 1
fi
sleep 4

# --- 5. Verify local API ---
info "Step 5: verify local API"
if curl -sf http://127.0.0.1:8000/api/health >/dev/null; then
  pass "curl http://127.0.0.1:8000/api/health"
else
  fail "New API health check failed"
  journalctl -u worldcup-api -n 40 --no-pager 2>&1 | sed -E 's/(password|secret|key|token)=[^ ]+/REDACTED/gi'
  rollback_old_api
  exit 1
fi

# --- 6. Nginx IP-first ---
info "Step 6: configure nginx"
if [[ -f "$NGINX_AVAIL" ]]; then
  cp -a "$NGINX_AVAIL" "$NGINX_BAK"
fi
sed "s/YOUR_SERVER_IP/$IP/g" "$APP/deployment/nginx/worldcup-ip.conf" > "$NGINX_AVAIL"
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
# Disable default if it conflicts on port 80
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
if nginx -t 2>&1; then
  systemctl reload nginx
  pass "nginx configured and reloaded"
else
  fail "nginx -t failed"
  if [[ -f "$NGINX_BAK" ]]; then cp -a "$NGINX_BAK" "$NGINX_AVAIL"; fi
  rollback_old_api
  exit 1
fi

# --- 7. Public IP checks ---
info "Step 7: public IP verification"
if curl -sf "http://$IP/api/health" >/dev/null; then
  pass "http://$IP/api/health"
else
  fail "Public API health failed"
fi
if curl -sf "http://$IP/" | head -c 200 | grep -qi html; then
  pass "http://$IP/ serves frontend HTML"
else
  fail "Public frontend root failed"
fi

echo "=== Phase 2 infrastructure complete ==="
