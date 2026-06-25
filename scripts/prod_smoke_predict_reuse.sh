#!/usr/bin/env bash
FID="${1:-1539007}"
echo "POST predict reuse test fixture $FID"
curl -sf -X POST "http://127.0.0.1:8000/api/predict/${FID}?competition=world_cup_2026&season=2026" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('cache_source=',d.get('cache_source')); print('pick_tier=',d.get('pick_tier')); print('no_bet=',d.get('no_bet')); print('confidence=',d.get('confidence')); rb=d.get('recommended_bets') or []; print('rec0=', rb[0].get('status') if rb else None, rb[0].get('display_text','')[:60] if rb else '')"
