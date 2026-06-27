#!/usr/bin/env bash
# Phase A19 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check watchlist "$BASE/watchlist"
check notifications "$BASE/notifications"
check briefing "$BASE/daily-briefing"
check paper "$BASE/paper-betting"
check betting_plan "$BASE/betting-plan"
check matches "$BASE/matches"
check api_watchlist "$BASE/api/watchlist"
check api_briefing "$BASE/api/daily-briefing"
echo "SMOKE_OK"
