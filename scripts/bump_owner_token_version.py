#!/usr/bin/env python3
"""Force owner re-login by bumping token_version (SQL-safe for older repos)."""

from __future__ import annotations

import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from sqlalchemy import text

from worldcup_predictor.database.postgres.session import get_postgres_engine
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

DEFAULT_EMAIL = "kamangar.pedram@gmail.com"


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL).strip().lower()
    if not postgres_configured():
        print("DATABASE_URL not configured", file=sys.stderr)
        return 1

    new_tv = None
    try:
        with saas_uow() as uow:
            user = uow.users.get_by_email(email)
            if user is None:
                print(f"NOT_FOUND: {email}", file=sys.stderr)
                return 1
            if hasattr(uow.users, "bump_token_version"):
                new_tv = uow.users.bump_token_version(user.id)
            else:
                raise AttributeError("bump_token_version missing")
    except AttributeError:
        engine = get_postgres_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE users SET token_version = COALESCE(token_version, 0) + 1 "
                    "WHERE lower(email) = lower(:email)"
                ),
                {"email": email},
            )
            row = conn.execute(
                text("SELECT token_version, role::text FROM users WHERE lower(email) = lower(:email)"),
                {"email": email},
            ).fetchone()
            new_tv = row[0] if row else None
            role = row[1] if row else "?"
            print("TOKEN_BUMP_OK")
            print(email)
            print(role)
            print(str(new_tv))
            return 0

    print("TOKEN_BUMP_OK")
    print(email)
    print("owner")
    print(str(new_tv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
