#!/usr/bin/env bash
# Diagnose owner password state — no plaintext output.
set -euo pipefail
APP=/opt/worldcup-predictor
EMAIL=kamangar.pedram@gmail.com
cd "$APP"
set -a && source .env.production && set +a
export PYTHONPATH="$APP"

"$APP/.venv/bin/python" <<'PY'
import os
from pathlib import Path
from sqlalchemy import text
from worldcup_predictor.database.postgres.session import get_postgres_engine
from worldcup_predictor.auth.passwords import verify_password

email = "kamangar.pedram@gmail.com"
engine = get_postgres_engine()
with engine.connect() as conn:
    row = conn.execute(
        text(
            "SELECT email, role::text, email_verified, is_active, is_banned, "
            "token_version, updated_at, left(password_hash, 7) AS hash_prefix "
            "FROM users WHERE lower(email)=lower(:e)"
        ),
        {"e": email},
    ).fetchone()

if not row:
    print("OWNER_FOUND=no")
    raise SystemExit(1)

print("OWNER_FOUND=yes")
print(f"ROLE={row[1]}")
print(f"EMAIL_VERIFIED={row[2]}")
print(f"IS_ACTIVE={row[3]}")
print(f"IS_BANNED={row[4]}")
print(f"TOKEN_VERSION={row[5]}")
print(f"UPDATED_AT={row[6]}")
print(f"HASH_PREFIX={row[7]}")

with engine.connect() as conn:
    full = conn.execute(
        text("SELECT password_hash FROM users WHERE lower(email)=lower(:e)"),
        {"e": email},
    ).scalar()

candidates = {
    "phase41c_file": Path("/root/.wcp_phase41c_owner_login.txt"),
    "phase40a_file": Path("/root/.wcp_phase40a_owner_initial.txt"),
    "requested_file": Path("/root/.wcp_owner_requested_password.txt"),
}

for label, path in candidates.items():
    if path.is_file():
        pwd = path.read_text().strip("\r\n")
        match = verify_password(pwd, full) if full else False
        print(f"CANDIDATE_{label}=exists len={len(pwd)} matches_db={str(match).lower()}")
    else:
        print(f"CANDIDATE_{label}=missing")

env_req = (os.environ.get("OWNER_REQUESTED_PASSWORD") or "").strip()
if env_req:
    print(f"CANDIDATE_env_requested=set len={len(env_req)} matches_db={str(verify_password(env_req, full)).lower()}")
else:
    print("CANDIDATE_env_requested=unset")
PY
