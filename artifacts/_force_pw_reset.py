from sqlalchemy import text

from worldcup_predictor.auth.passwords import hash_password, verify_password
from worldcup_predictor.database.postgres.session import get_postgres_engine

email = "kamangar.pedram@gmail.com"
pwd = open("/root/.wcp_phase41c_owner_login.txt").read().strip("\r\n")
new_hash = hash_password(pwd)

engine = get_postgres_engine()
with engine.begin() as conn:
    old = conn.execute(
        text("SELECT password_hash FROM users WHERE lower(email)=lower(:e)"),
        {"e": email},
    ).fetchone()
    print("old_hash_prefix", (old[0] or "")[:20] if old else None)
    conn.execute(
        text(
            """
            UPDATE users
            SET password_hash = :pwd,
                role = 'owner',
                email_verified = true,
                is_active = true,
                is_banned = false,
                token_version = COALESCE(token_version, 0) + 1
            WHERE lower(email) = lower(:email)
            """
        ),
        {"email": email, "pwd": new_hash},
    )
    row = conn.execute(
        text("SELECT password_hash FROM users WHERE lower(email)=lower(:e)"),
        {"e": email},
    ).fetchone()
    print("new_hash_prefix", (row[0] or "")[:20])
    print("verify_after_sql", verify_password(pwd, row[0]))
