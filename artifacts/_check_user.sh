#!/usr/bin/env bash
set -euo pipefail
cd /opt/worldcup-predictor
set -a
source .env.production
set +a
.venv/bin/python <<'PY'
from sqlalchemy import text
from worldcup_predictor.database.postgres.session import get_postgres_engine

email = "kamangar.pedram@gmail.com"
engine = get_postgres_engine()
with engine.connect() as conn:
    row = conn.execute(
        text(
            "SELECT email, role::text, email_verified, is_active, is_banned, token_version "
            "FROM users WHERE lower(email)=lower(:e)"
        ),
        {"e": email},
    ).fetchone()
print("ROW:", row)
PY
