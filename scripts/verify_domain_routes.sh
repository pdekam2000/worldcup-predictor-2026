#!/usr/bin/env bash
HOST="${1:-footballpredictor.it.com}"
for p in /login /register /dashboard /matches /; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$HOST$p")
  echo "PASS route https://$HOST$p HTTP $code"
done
echo "--- redirect ---"
curl -sI "http://$HOST/" | head -2
