#!/usr/bin/env bash
# Phase 4 — Post-deploy cleanup verification and IP redirect
set -uo pipefail

DOMAIN="footballpredictor.it.com"
IP="91.107.188.229"
APP="/opt/worldcup-predictor"
WEB="/var/www/worldcup/frontend/dist"

pass() { printf 'PASS\t%s\n' "$1"; }
fail() { printf 'FAIL\t%s\n' "$1"; }
info() { printf 'INFO\t%s\n' "$1"; }

echo "=== Phase 4 Post-Deploy ==="

# 1-2. Google login UI in deployed bundle
if grep -rq 'Continue with Google' "$WEB" 2>/dev/null; then
  fail "Google button still in deployed frontend"
else
  pass "Google OAuth button not in deployed bundle"
fi
if grep -rq 'Google login coming soon' "$WEB/assets/" 2>/dev/null; then
  pass "Google login coming soon text in bundle"
else
  fail "Coming soon text missing from bundle"
fi

# 6. IP redirect to domain
REDIRECT=$(curl -sI "http://$IP/" 2>/dev/null | grep -i '^location:' | tr -d '\r')
if echo "$REDIRECT" | grep -qi "https://$DOMAIN"; then
  pass "IP http://$IP redirects to https://$DOMAIN"
else
  fail "IP redirect: ${REDIRECT:-none}"
fi

# 7. SSL auto-renew
if systemctl is-active --quiet certbot.timer; then
  pass "certbot.timer active"
else
  fail "certbot.timer not active"
fi
if certbot renew --dry-run 2>&1 | grep -q 'Congratulations'; then
  pass "certbot renew dry-run OK"
elif certbot renew --dry-run 2>&1 | grep -qi 'success'; then
  pass "certbot renew dry-run OK"
else
  info "certbot dry-run output logged (check manually if needed)"
  certbot renew --dry-run 2>&1 | tail -3
fi

# 8. Service status
for svc in nginx worldcup-api; do
  if systemctl is-active --quiet "$svc"; then
    pass "$svc active"
  else
    fail "$svc not active"
  fi
done

# 8. Recent errors in logs (last 30 min, no secrets)
NGINX_ERR=$(journalctl -u nginx --since "30 min ago" -p err --no-pager 2>/dev/null | wc -l)
API_ERR=$(journalctl -u worldcup-api --since "30 min ago" -p err --no-pager 2>/dev/null | wc -l)
if [[ "$NGINX_ERR" -eq 0 ]]; then
  pass "nginx: no error-level journal entries (30 min)"
else
  info "nginx error journal lines: $NGINX_ERR"
fi
if [[ "$API_ERR" -eq 0 ]]; then
  pass "worldcup-api: no error-level journal entries (30 min)"
else
  info "worldcup-api error journal lines: $API_ERR"
fi

# 5. Route checks (HTTPS SPA)
ROUTES="/ /login /register /dashboard /matches /accuracy /history /favorites /alerts /subscription /notifications /settings /privacy /terms /contact"
ROUTE_FAIL=0
for p in $ROUTES; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN$p")
  if [[ "$code" == "200" ]]; then
    pass "route $p HTTP $code"
  else
    fail "route $p HTTP $code"
    ROUTE_FAIL=$((ROUTE_FAIL + 1))
  fi
done

# 9. Live SaaS API smoke test
if [[ -f /tmp/verify_domain_ssl.sh ]]; then
  bash /tmp/verify_domain_ssl.sh 2>/dev/null | grep -E '^PASS|^FAIL' || true
fi

# HTTPS health
curl -sf "https://$DOMAIN/api/health" >/dev/null && pass "https://$DOMAIN/api/health" || fail "API health"

# Certificate expiry
certbot certificates 2>/dev/null | grep -A1 "Expiry Date" | head -2 | sed 's/^/  /'

echo "=== Phase 4 verification complete ==="
