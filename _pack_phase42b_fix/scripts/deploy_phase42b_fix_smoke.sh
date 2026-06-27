#!/usr/bin/env bash
# Phase 42B-FIX production smoke
set -euo pipefail

LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
PUBLIC_URL="${PUBLIC_URL:-https://footballpredictor.it.com}"

fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Phase 42B-FIX smoke ==="

HEALTH=$(curl -sS -o /tmp/phase42b_fix_health.json -w '%{http_code}' "${LOCAL_API}/api/health")
[ "$HEALTH" = "200" ] || fail "health status=${HEALTH}"
pass "/api/health 200"

SUMMARY=$(curl -sS -o /tmp/phase42b_fix_summary.json -w '%{http_code}' "${LOCAL_API}/api/accuracy/summary")
[ "$SUMMARY" = "200" ] || fail "accuracy summary status=${SUMMARY}"
pass "/api/accuracy/summary 200"

PAGE=$(curl -sS -o /dev/null -w '%{http_code}' "${PUBLIC_URL}/accuracy")
[ "$PAGE" = "200" ] || fail "/accuracy page status=${PAGE}"
pass "/accuracy page 200"

python3 <<'PY'
import json
from pathlib import Path
from worldcup_predictor.prediction.market_consistency_guard import apply_market_consistency_guard

sample = {
    "status": "ok",
    "home_team": "A",
    "away_team": "B",
    "detailed_markets": {
        "match_winner": {"selection": "home_win", "probabilities": {"home_win": 60, "draw": 20, "away_win": 20}},
        "over_under_25": {"selection": "under_2_5", "probability": 0.8, "probabilities": {"over_2_5": 20, "under_2_5": 80}},
        "btts": {"selection": "no", "probability": 0.8, "probabilities": {"yes": 20, "no": 80}},
        "first_goal": {"team": "A", "minute_range": "16-30", "expected_minute": 38},
        "goalscorer": {"available": True, "player": "X", "team": "B", "confidence": 0.4},
        "correct_scores": [{"label": "2-1", "probability": 15}],
    },
    "sportmonks_xg": {"away_xg": 0.2},
}
out = apply_market_consistency_guard(sample)
cg = out.get("consistency_guard") or {}
assert cg.get("applied") is True
fg = out["detailed_markets"]["first_goal"]
assert fg.get("minute_range") == "31-45", fg
print("consistency_guard_applied=True timing_aligned=", fg.get("minute_range"))
PY
pass "consistency guard active on server module"

BUNDLE=$(python3 <<'PY'
import re
from pathlib import Path
html = Path("/var/www/worldcup/frontend/dist/index.html").read_text()
m = re.search(r'/assets/(index-[^"]+\.js)', html)
print(m.group(1) if m else "")
PY
)
BUNDLE="/var/www/worldcup/frontend/dist/assets/${BUNDLE}"
if [ -n "$BUNDLE" ] && [ -f "$BUNDLE" ]; then
  if grep -qE 'display_allowed|WithheldMarketPanel|conflicts with stronger model signals' "$BUNDLE" 2>/dev/null; then
    pass "frontend bundle includes consistency guard UX"
  else
    fail "frontend bundle missing consistency guard UX"
  fi
fi

echo "SMOKE_ALL_PASS"
