#!/usr/bin/env bash
set -uo pipefail
echo "=== DB diagnostic (no secrets) ==="
test -f /opt/worldcup-predictor/.env && echo "WARN: .env exists (may override settings)" || echo "OK: no .env file"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='worldcup_user'" | grep -q 1 && echo "PASS: worldcup_user role exists" || echo "FAIL: worldcup_user missing"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='worldcup_predictor'" | grep -q 1 && echo "PASS: worldcup_predictor db exists" || echo "FAIL: db missing"
grep '^DATABASE_URL' /opt/worldcup-predictor/.env.production | grep -q '"' && echo "WARN: DATABASE_URL contains double quotes" || echo "OK: no quotes in DATABASE_URL line"
grep '^DATABASE_URL' /opt/worldcup-predictor/.env.production | grep -q "'" && echo "WARN: DATABASE_URL contains single quotes" || echo "OK: no single quotes"
bash /tmp/test_db_connection_server.sh 2>/dev/null || true
