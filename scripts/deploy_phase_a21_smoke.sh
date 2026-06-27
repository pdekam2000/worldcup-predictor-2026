#!/usr/bin/env bash
# Phase A21 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check home "$BASE/"
check matches "$BASE/matches"
check combo "$BASE/combo-tips"
check betting_plan "$BASE/betting-plan"
check paper "$BASE/paper-betting"
check watchlist "$BASE/watchlist"
check briefing "$BASE/daily-briefing"
check archive "$BASE/archive"
check accuracy "$BASE/accuracy"
check public_accuracy "$BASE/public/accuracy"
check predops "$BASE/admin/predops"
check api_health "$BASE/api/health"
check api_plan "$BASE/api/betting-plan/today"
check api_public_acc "$BASE/api/public/accuracy"
echo "SMOKE_OK"
