#!/usr/bin/env bash
# Phase A18 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check paper "$BASE/paper-betting"
check api_account "$BASE/api/paper-betting/account"
check api_summary "$BASE/api/paper-betting/summary"
check betting_plan "$BASE/betting-plan"
check archive "$BASE/archive"
check accuracy "$BASE/accuracy"
echo "SMOKE_OK"
