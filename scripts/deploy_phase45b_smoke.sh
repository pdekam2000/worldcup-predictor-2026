#!/usr/bin/env bash
# Phase 45B production smoke tests
set -euo pipefail

BASE="${BASE_URL:-https://footballpredictor.it.com}"
echo "Smoke base: ${BASE}"

curl -fsS "${BASE}/api/health" | head -c 200
echo ""
curl -fsS -o /dev/null -w "accuracy HTTP %{http_code}\n" "${BASE}/accuracy"
curl -fsS -o /dev/null -w "history HTTP %{http_code}\n" "${BASE}/history"
curl -fsS -o /dev/null -w "dashboard HTTP %{http_code}\n" "${BASE}/dashboard"
curl -fsS "${BASE}/api/performance/summary" | python3 -c "import sys,json; d=json.load(sys.stdin); print('evaluated', d.get('total_evaluated'), 'accuracy', d.get('overall_accuracy'))"
curl -fsS "${BASE}/api/billing/status" | python3 -c "import sys,json; d=json.load(sys.stdin); print('stripe_mode', d.get('stripe_mode') or d.get('mode') or d.get('live_mode'))" 2>/dev/null || echo "billing status check skipped"
echo "SMOKE_OK"
