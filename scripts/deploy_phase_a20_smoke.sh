#!/usr/bin/env bash
# Phase A20 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check share_pick "$BASE/share/pick/test"
check share_combo "$BASE/share/combo/test"
check public_accuracy "$BASE/public/accuracy"
check api_accuracy "$BASE/api/public/accuracy"
check betting_plan "$BASE/betting-plan"
check combo "$BASE/combo-tips"
echo "SMOKE_OK"
