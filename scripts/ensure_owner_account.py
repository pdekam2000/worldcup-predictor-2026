#!/usr/bin/env python3
"""Phase 63 — ensure owner account (SQL-safe for older production repos)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from sqlalchemy import text

from worldcup_predictor.api.web_auth import seed_owner_account
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.database.postgres.session import get_postgres_engine
from worldcup_predictor.database.saas_factory import postgres_configured

DEFAULT_EMAIL = "kamangar.pedram@gmail.com"
MIN_PASSWORD_LENGTH = 8


def ensure_owner_account_sql(email: str) -> int:
    normalized = email.strip().lower()
    engine = get_postgres_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE users
                SET role = 'owner',
                    email_verified = true,
                    is_active = true,
                    is_banned = false
                WHERE lower(email) = lower(:email)
                """
            ),
            {"email": normalized},
        )
        return int(result.rowcount or 0)


def ensure_owner_account(*, email: str, preserve_plan: bool = True) -> None:
    normalized = email.strip().lower()

    rows = 0
    if postgres_configured():
        try:
            rows = ensure_owner_account_sql(normalized)
        except Exception as exc:
            print(f"SQL owner update failed: {exc}", file=sys.stderr)

    if rows > 0:
        print("OWNER_ACCOUNT_OK")
        print(normalized)
        print("owner")
        print("true")
        print("true")
        print("false")
        return

    from worldcup_predictor.database.postgres.enums import SubscriptionPlan
    from worldcup_predictor.database.saas_factory import saas_uow

    with saas_uow() as uow:
        existing = uow.users.get_by_email(normalized)
        if existing is None:
            pwd_env = (os.environ.get("OWNER_LOGIN_PASSWORD") or "").strip()
            if len(pwd_env) < MIN_PASSWORD_LENGTH:
                print(
                    "Owner not found. Set OWNER_LOGIN_PASSWORD to create, or run migration first.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            seed_owner_account(
                email=normalized,
                password_hash=hash_password(pwd_env),
                full_name=normalized.split("@")[0],
                plan=SubscriptionPlan.PRO,
            )
        else:
            try:
                uow.users.set_email_verified(existing.id, True)
                uow.users.clear_ban(existing.id)
                uow.users.set_active(existing.id, True)
                from worldcup_predictor.database.postgres.enums import UserRole

                uow.users.set_role(existing.id, UserRole.OWNER)
            except AttributeError:
                ensure_owner_account_sql(normalized)

    print("OWNER_ACCOUNT_OK")
    print(normalized)
    print("owner")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure owner account (Phase 63).")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    args = parser.parse_args()

    if not postgres_configured():
        print("PostgreSQL DATABASE_URL is not configured.", file=sys.stderr)
        return 1

    ensure_owner_account(email=args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
