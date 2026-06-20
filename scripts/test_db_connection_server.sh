#!/usr/bin/env bash
# Test PostgreSQL connection from .env.production without printing secrets.
set -uo pipefail
cd /opt/worldcup-predictor
set -a
source .env.production
set +a
.venv/bin/python <<'PY'
import os
import sys
from urllib.parse import urlparse, unquote

url = (os.environ.get("DATABASE_URL") or "").strip()
if not url:
    print("FAIL\tDATABASE_URL empty")
    sys.exit(1)

parsed = urlparse(url)
user = parsed.username or ""
host = parsed.hostname or ""
port = parsed.port or 5432
dbname = (parsed.path or "").lstrip("/")
has_password = bool(parsed.password)
print(f"INFO\tuser={user} host={host} port={port} db={dbname} password_set={has_password}")

if not has_password:
    print("FAIL\tDATABASE_URL has no password segment")
    sys.exit(1)

# Raw password from URL (may need unquote if user URL-encoded)
password = unquote(parsed.password or "")

try:
    import psycopg
    conn = psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
    )
    conn.close()
    print("PASS\tpsycopg direct connection OK")
except Exception as e:
    msg = str(e).split("\n")[0]
    print(f"FAIL\tpsycopg direct: {msg}")
    sys.exit(1)
PY
