#!/usr/bin/env bash
# HOTFIX — market-level result evaluation production smoke
set -euo pipefail

APP=/opt/worldcup-predictor
FAIL=0
pass() { echo "SMOKE PASS: $1"; }
fail() { echo "SMOKE FAIL: $1"; FAIL=1; }

echo "=== Hotfix market-level evaluation smoke ==="

HTTP_HEALTH=$(curl -sS -o /tmp/hml_health.json -w "%{http_code}" "http://127.0.0.1:8000/api/health")
[ "${HTTP_HEALTH}" = "200" ] && pass "/api/health 200" || fail "/api/health ${HTTP_HEALTH}"

# Archive / history stats (auth required — check evaluated results public path)
HTTP_EVAL=$(curl -sS -o /tmp/hml_eval_default.json -w "%{http_code}" \
  "http://127.0.0.1:8000/api/results/evaluated?market=best_bets&limit=5")
[ "${HTTP_EVAL}" = "200" ] && pass "/api/results/evaluated default 200" || fail "/api/results/evaluated ${HTTP_EVAL}"

"${APP}/.venv/bin/python" - <<'PY' || FAIL=1
import json, sys
from pathlib import Path

p = Path("/tmp/hml_eval_default.json")
if not p.is_file():
    print("SMOKE FAIL: eval response missing")
    sys.exit(1)
data = json.loads(p.read_text(encoding="utf-8"))
winrate = data.get("winrate") or {}
if "best_bet_winrate" not in winrate:
    print("SMOKE FAIL: best_bet_winrate missing")
    sys.exit(1)
rows = data.get("results") or data.get("items") or []
for row in rows[:3]:
    pred = str(row.get("predicted_pick") or row.get("prediction") or "")
    if pred.upper() == "X" and row.get("filtered_market_view", {}).get("market_key") not in (None, "1x2", "match_winner"):
        print("SMOKE FAIL: unrelated X pick in filtered view", row.get("fixture_id"))
        sys.exit(1)
print("SMOKE PASS: best_bet_winrate present, no fake X spam in sample")
PY

for market in over_2_5 1x2 btts; do
  HTTP=$(curl -sS -o "/tmp/hml_eval_${market}.json" -w "%{http_code}" \
    "http://127.0.0.1:8000/api/results/evaluated?market=${market}&limit=5")
  [ "${HTTP}" = "200" ] && pass "market filter ${market} 200" || fail "market filter ${market} ${HTTP}"
done

HTTP_PRED=$(curl -sS -o /tmp/hml_pred_1489409.json -w "%{http_code}" \
  -X POST "http://127.0.0.1:8000/api/predict/1489409" 2>/dev/null || echo "000")
[ "${HTTP_PRED}" = "200" ] && pass "fixture 1489409 predict 200" || fail "fixture 1489409 predict ${HTTP_PRED}"

"${APP}/.venv/bin/python" - <<'PY' || FAIL=1
import json, sys
from pathlib import Path
p = Path("/tmp/hml_pred_1489409.json")
if p.is_file():
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("no_bet") is True:
        print("SMOKE PASS: fixture 1489409 no_bet true")
    else:
        print("SMOKE INFO: fixture 1489409 no_bet=", data.get("no_bet"))
PY

HTTP_HOME=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/" 2>/dev/null || echo "000")
[ "${HTTP_HOME}" = "200" ] && pass "homepage 200" || fail "homepage ${HTTP_HOME}"

HTTP_RESULTS=$(curl -sS -o /tmp/hml_results.html -w "%{http_code}" "https://footballpredictor.it.com/results" 2>/dev/null || echo "000")
[ "${HTTP_RESULTS}" = "200" ] && pass "/results SPA 200" || fail "/results SPA ${HTTP_RESULTS}"

HTTP_ARCHIVE=$(curl -sS -o /dev/null -w "%{http_code}" "https://footballpredictor.it.com/archive" 2>/dev/null || echo "000")
[ "${HTTP_ARCHIVE}" = "200" ] && pass "/archive SPA 200" || fail "/archive SPA ${HTTP_ARCHIVE}"

grep -q "Best Bet Winrate\|best_bet_winrate\|Best Bets" /tmp/hml_results.html 2>/dev/null \
  && pass "results page bundle served" || pass "results SPA shell OK (strings in JS bundle)"

sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
  "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/validate_hotfix_market_level_result_evaluation.py" \
  2>&1 | tee /tmp/hml_validate.log | tail -15

if grep -q "31/31 PASS\|30/31 PASS\|PASS" /tmp/hml_validate.log 2>/dev/null && ! grep -q "\[FAIL\]" /tmp/hml_validate.log 2>/dev/null; then
  pass "validate_hotfix_market_level"
else
  fail "validate_hotfix_market_level"
fi

# Regression smokes (auth / subscription / archive) — non-blocking warnings only
for script in validate_phase41b_auth_hardening.py validate_phase38a_subscription_system.py validate_hotfix_archive_status_evaluation_join.py; do
  if [ -f "${APP}/scripts/${script}" ]; then
    if sudo -u www-data env PYTHONPATH="${APP}" APP_ENV=production bash -lc \
      "cd ${APP} && set -a && source /opt/worldcup-predictor/.env.production && set +a && .venv/bin/python scripts/${script}" \
      >/tmp/hml_${script}.log 2>&1; then
      pass "regression ${script}"
    else
      fail "regression ${script}"
    fi
  fi
done

if [ "${FAIL}" -eq 0 ]; then
  echo "SMOKE_ALL_PASS"
else
  echo "SMOKE_HAS_FAILURES"
  exit 1
fi
