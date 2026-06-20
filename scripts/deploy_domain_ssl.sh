#!/usr/bin/env bash
# Domain + SSL setup for footballpredictor.it.com
set -uo pipefail

DOMAIN="footballpredictor.it.com"
IP="91.107.188.229"
APP="/opt/worldcup-predictor"
WEB="/var/www/worldcup/frontend/dist"
NGINX_SITE="/etc/nginx/sites-available/worldcup"
NGINX_ENABLED="/etc/nginx/sites-enabled/worldcup"
NGINX_IP="/etc/nginx/sites-enabled/worldcup-ip"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }
info() { printf 'INFO\t%s\n' "$1"; }

echo "=== Domain + SSL: $DOMAIN ==="

# 1. DNS check from server
RESOLVED=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}')
if [[ "$RESOLVED" == "$IP" ]]; then
  pass "DNS $DOMAIN -> $IP"
else
  fail "DNS $DOMAIN -> ${RESOLVED:-unknown} (expected $IP)"
  exit 1
fi

# 2. Install certbot
export DEBIAN_FRONTEND=noninteractive
if command -v certbot >/dev/null 2>&1; then
  pass "certbot already installed: $(certbot --version 2>&1 | head -1)"
else
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx
  if command -v certbot >/dev/null; then
    pass "certbot installed"
  else
    fail "certbot install failed"
    exit 1
  fi
fi

mkdir -p /var/www/certbot

# 3. HTTP nginx config (pre-SSL) — certbot will add HTTPS + redirect
cat > "$NGINX_SITE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    client_max_body_size 10M;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    root $WEB;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)\$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
        try_files \$uri =404;
    }
}
NGINX

ln -sf "$NGINX_SITE" "$NGINX_ENABLED"
# Keep IP access via separate site (optional)
if [[ -L "$NGINX_IP" ]]; then
  info "Keeping worldcup-ip for direct IP access"
fi

if nginx -t 2>&1; then
  systemctl reload nginx
  pass "nginx HTTP config for $DOMAIN"
else
  fail "nginx -t failed"
  exit 1
fi

# 4. Obtain certificate
if [[ -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  pass "Certificate already exists for $DOMAIN"
  certbot renew --dry-run 2>&1 | tail -1 || true
else
  info "Requesting Let's Encrypt certificate..."
  if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
      --register-unsafely-without-email --redirect --no-eff-email 2>&1; then
    pass "Let's Encrypt certificate obtained"
  else
    fail "certbot failed — check DNS and port 80"
    exit 1
  fi
fi

# 5. Verify cert files
if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
  pass "Certificate files present"
  certbot certificates 2>/dev/null | grep -A2 "$DOMAIN" | sed 's/^/  /' || true
else
  fail "Certificate files missing"
  exit 1
fi

# 6. Ensure nginx reloaded
nginx -t && systemctl reload nginx
if systemctl is-active --quiet nginx; then
  pass "nginx active"
else
  fail "nginx not active"
fi

# 7. HTTP -> HTTPS redirect
REDIRECT=$(curl -sI "http://$DOMAIN/" 2>/dev/null | head -1)
if echo "$REDIRECT" | grep -qE '301|302|308'; then
  pass "HTTP redirects to HTTPS"
else
  info "Redirect header: $REDIRECT"
fi

# 8. HTTPS health
if curl -sf "https://$DOMAIN/api/health" >/dev/null; then
  pass "https://$DOMAIN/api/health"
else
  fail "HTTPS API health failed"
fi

if curl -sf "https://$DOMAIN/" | head -c 100 | grep -qi html; then
  pass "https://$DOMAIN/ frontend"
else
  fail "HTTPS frontend failed"
fi

echo "=== Domain + SSL setup complete ==="
