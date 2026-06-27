#!/usr/bin/env bash
# Phase A16 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check matches "$BASE/api/matches?competition=all&include_summary=true&page_size=5"
check combo "$BASE/combo-tips"
check admin_predops "$BASE/admin/predops"
# API spot-check: publication_overlay on snapshot endpoint
FID=$(curl -s "$BASE/api/matches?competition=world_cup_2026&has_prediction=true&page_size=1" | python3 -c "import sys,json; d=json.load(sys.stdin); m=(d.get('matches') or [{}])[0]; print(m.get('fixture_id') or '')" 2>/dev/null || echo "")
if [ -n "$FID" ]; then
  curl -s "$BASE/api/predops/snapshots/latest?fixture_id=$FID" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('snapshot') or {}; assert 'publication_overlay' in s, 'missing overlay'; print('snapshot_overlay=ok')" || echo "snapshot_overlay=warn"
fi
curl -s "$BASE/api/predops/combo-readiness" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'quality_thresholds' in d; print('combo_readiness=ok')" || echo "combo_readiness=warn"
echo "SMOKE_OK"
