#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-https://footballpredictor.it.com}"

echo "=== Phase A12 smoke ==="
curl -fsS "${BASE}/api/performance/summary?competition=world_cup_2026" | head -c 400
echo ""
curl -fsS -o /dev/null -w "archive_page=%{http_code}\n" "${BASE}/archive"
curl -fsS -o /dev/null -w "accuracy_page=%{http_code}\n" "${BASE}/accuracy"
echo "SMOKE_OK"
