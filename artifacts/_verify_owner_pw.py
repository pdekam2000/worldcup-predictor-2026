import os
from pathlib import Path

from sqlalchemy import text

from worldcup_predictor.auth.passwords import verify_password
from worldcup_predictor.database.postgres.session import get_postgres_engine

email = "kamangar.pedram@gmail.com"
pw_file = Path("/root/.wcp_phase41c_owner_login.txt")
pwd = pw_file.read_text().strip("\r\n")
print("pwd_len", len(pwd))

engine = get_postgres_engine()
with engine.connect() as conn:
    row = conn.execute(
        text("SELECT password_hash FROM users WHERE lower(email)=lower(:e)"),
        {"e": email},
    ).fetchone()
print("hash_exists", bool(row and row[0]))
if row and row[0]:
    ok = verify_password(pwd, row[0])
    print("verify_password", ok)
