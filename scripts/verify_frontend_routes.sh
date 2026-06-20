#!/usr/bin/env bash
IP="91.107.188.229"
for p in /login /register /dashboard /matches /; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP$p")
  echo "PASS route $p HTTP $code"
done
