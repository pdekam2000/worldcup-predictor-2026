#!/usr/bin/env bash
set -euo pipefail
NGINX_CONF=/etc/nginx/nginx.conf
NGINX_SITE=/etc/nginx/sites-enabled/worldcup
if ! grep -q 'zone=gpt_actions' "$NGINX_CONF"; then
  sed -i '/^http {/a \    limit_req_zone $binary_remote_addr zone=gpt_actions:10m rate=30r/m;' "$NGINX_CONF"
fi
if ! grep -q '/api/gpt-actions/v1/' "$NGINX_SITE"; then
  SNIP=/opt/worldcup-predictor/deployment/nginx/gpt-actions-snippet.conf
  awk -v snip="$SNIP" '
    BEGIN { while ((getline line < snip) > 0) snippet = snippet line "\n" }
    /location \/api\/ \{/ && !done { print snippet; done=1 }
    { print }
  ' "$NGINX_SITE" > "${NGINX_SITE}.phase5.tmp"
  mv "${NGINX_SITE}.phase5.tmp" "$NGINX_SITE"
fi
nginx -t
systemctl reload nginx
echo NGINX_OK
