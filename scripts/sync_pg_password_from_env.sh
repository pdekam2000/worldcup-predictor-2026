#!/usr/bin/env bash
# Sync PostgreSQL worldcup_user password TO match DATABASE_URL in .env.production.
# Does not print secrets.
set -uo pipefail
cd /opt/worldcup-predictor
set -a && source .env.production && set +a

.venv/bin/python <<'PY'
import os
import subprocess
import sys
from urllib.parse import urlparse, unquote

url = (os.environ.get("DATABASE_URL") or "").strip()
parsed = urlparse(url)
password = unquote(parsed.password or "")
if not password:
    print("FAIL\tNo password in DATABASE_URL")
    sys.exit(1)

# Escape single quotes for SQL
sql_password = password.replace("'", "''")
sql = f"ALTER USER worldcup_user WITH PASSWORD '{sql_password}';"
result = subprocess.run(
    ["sudo", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-c", sql],
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print("FAIL\tALTER USER failed:", (result.stderr or result.stdout).strip().split("\n")[0])
    sys.exit(1)
print("PASS\tPostgreSQL password synced from .env.production")
PY

bash /tmp/test_db_connection_server.sh
