#!/usr/bin/env bash
# Phase A14 post-deploy smoke
set -eu
BASE="${1:-https://footballpredictor.it.com}"
check() { curl -s -o /dev/null -w "$1=%{http_code}\n" "$2"; }
check matches "$BASE/api/matches?competition=all&include_summary=true&page_size=5"
check combo "$BASE/combo-tips"
check owner_page "$BASE/owner/prefetch-coverage"
echo "SMOKE_OK"
