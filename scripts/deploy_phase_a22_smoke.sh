#!/usr/bin/env bash
# Phase A22 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check health "$BASE/api/health"
check matches "$BASE/matches"
check elite_shadow_page "$BASE/admin/elite-shadow"
echo "SMOKE_OK"
