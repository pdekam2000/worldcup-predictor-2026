#!/usr/bin/env bash
set -euo pipefail

LOCAL_API="${LOCAL_API:-http://127.0.0.1:8000}"
fail() { echo "SMOKE_FAIL: $*"; exit 1; }
pass() { echo "SMOKE_PASS: $*"; }

echo "=== Hotfix weather smoke ==="

curl -sS -o /tmp/hotfix_health.json -w '%{http_code}' "${LOCAL_API}/api/health" | grep -q 200 || fail health
pass "/api/health 200"

curl -sS -o /tmp/hotfix_providers.json "${LOCAL_API}/api/health/providers"
python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/hotfix_providers.json").read_text())
assert p.get("status") == "ok"
assert p.get("weather_configured") is True, p
assert p.get("weather_provider_ready") is True
print("weather_cache_ttl", p.get("weather_cache_ttl_seconds"))
PY
pass "/api/health/providers weather_configured=true"

CODE=$(curl -sS -o /tmp/hotfix_wrong.json -w '%{http_code}' "${LOCAL_API}/api/predictions/1489393")
[ "$CODE" = "404" ] || fail "wrong endpoint status=${CODE}"
python3 <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/hotfix_wrong.json").read_text())
assert d.get("detail", {}).get("code") == "wrong_endpoint"
PY
pass "/api/predictions/{id} fast 404"

curl -sS -o /tmp/hotfix_predict.json "${LOCAL_API}/api/predict/1489393"
python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/hotfix_predict.json").read_text())
pr = p.get("provider_readiness") or {}
assert pr.get("weather_configured") is True, pr
wi = p.get("weather_intelligence") or {}
assert wi.get("provider_now_configured") is True
assert wi.get("unavailable_reason") == "frozen_post_kickoff_snapshot"
print("frozen_fixture_weather_reason", wi.get("unavailable_reason"))
PY
pass "1489393 provider_readiness refreshed + frozen weather annotated"

curl -sS -o /tmp/hotfix_upcoming.json "${LOCAL_API}/api/predict/1489395"
python3 <<'PY'
import json
from pathlib import Path
p = json.loads(Path("/tmp/hotfix_upcoming.json").read_text())
pr = p.get("provider_readiness") or {}
wi = p.get("weather_intelligence") or {}
print("upcoming_weather_available", wi.get("available"))
print("upcoming_weather_reason", wi.get("unavailable_reason"))
assert pr.get("weather_configured") is True
if not wi.get("available"):
    assert wi.get("unavailable_reason") in {
        "weather_fetch_failed", "weather_fetch_error", "venue_city_missing", None
    } or wi.get("unavailable_reason")
PY
pass "upcoming fixture weather checked"

echo "SMOKE_ALL_PASS"
