from sqlalchemy import text
from worldcup_predictor.database.postgres.session import get_postgres_engine

engine = get_postgres_engine()
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    print("total_users", total)
    rows = conn.execute(
        text(
            "SELECT email, role::text, email_verified, is_active, is_banned "
            "FROM users ORDER BY created_at DESC NULLS LAST LIMIT 20"
        )
    ).fetchall()
    for r in rows:
        print(r)
