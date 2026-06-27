#!/usr/bin/env bash
# Phase A17 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check betting_plan "$BASE/betting-plan"
check api_today "$BASE/api/betting-plan/today"
check api_portfolio "$BASE/api/betting-plan/portfolio?date=today&bankroll=100&profile=balanced"
check combo_tips "$BASE/combo-tips"
check matches "$BASE/api/matches?competition=world_cup_2026&page_size=3&include_summary=true"
check predops "$BASE/api/predops/combo-readiness"
echo "SMOKE_OK"
