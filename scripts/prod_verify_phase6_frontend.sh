#!/usr/bin/env bash
set -euo pipefail

ORIGIN="https://footballpredictor.it.com"
PASS=0
FAIL=0

check() {
  local name="$1"
  local ok="$2"
  if [ "$ok" = "1" ]; then
    echo "PASS: $name"
    PASS=$((PASS+1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL+1))
  fi
}

# Health (backend untouched)
HEALTH=$(curl -sS -o /tmp/health.json -w "%{http_code}" "$ORIGIN/api/health")
check "GET /api/health 200" "$([ "$HEALTH" = "200" ] && echo 1 || echo 0)"
cat /tmp/health.json
echo

# worldcup-api not restarted in this deploy
check "worldcup-api still active (no restart)" "$(systemctl is-active worldcup-api | grep -q active && echo 1 || echo 0)"

# Fetch index + main JS bundle
curl -sS "$ORIGIN/" -o /tmp/index.html
JS=$(grep -oE 'assets/[^"]+\.js' /tmp/index.html | head -1)
check "index.html serves" "$([ -n "$JS" ] && echo 1 || echo 0)"
echo "bundle: $JS"

curl -sS "$ORIGIN/$JS" -o /tmp/main.js

for needle in TeamBadge DataQualityBadge PredictionCacheBanner teamFlags specialistReasons; do
  if grep -q "$needle" /tmp/main.js; then
    check "bundle contains $needle" 1
  else
    check "bundle contains $needle" 0
  fi
done

# SPA routes return index.html
for path in /matches /dashboard; do
  CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$ORIGIN$path")
  check "GET $path returns 200" "$([ "$CODE" = "200" ] && echo 1 || echo 0)"
done

# Quota protection (read-only validation)
cd /opt/worldcup-predictor
set -a
source .env.production 2>/dev/null || true
set +a
if python3 scripts/validate_quota_protection.py >/tmp/quota.txt 2>&1; then
  check "validate_quota_protection.py" 1
  grep -E "PASS|FAIL|passed" /tmp/quota.txt | tail -3
else
  check "validate_quota_protection.py" 0
  tail -5 /tmp/quota.txt
fi

echo "=== SUMMARY pass=$PASS fail=$FAIL ==="
