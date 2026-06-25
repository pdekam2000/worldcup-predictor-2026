#!/usr/bin/env python3
"""Phase 63 — apply enterprise RBAC migration without Alembic (production-safe)."""

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

from worldcup_predictor.database.postgres.session import get_postgres_engine
from worldcup_predictor.database.saas_factory import postgres_configured

DEFAULT_OWNER = "kamangar.pedram@gmail.com"
ENUM_VALUES = ("super_admin", "guest", "free_user", "starter", "pro", "premium", "owner")


def _promote_admins_to_super(conn, owner_email: str, promote_admins: bool) -> int:
    if not promote_admins:
        return 0
    result = conn.execute(
        text(
            """
            UPDATE users
            SET role = 'super_admin'
            WHERE role = 'admin'
              AND lower(email) <> lower(:owner)
            """
        ),
        {"owner": owner_email},
    )
    return int(result.rowcount or 0)


def migrate_roles(
    *,
    owner_email: str = DEFAULT_OWNER,
    promote_admins: bool = True,
    dry_run: bool = False,
) -> None:
    if not postgres_configured():
        print("PostgreSQL DATABASE_URL is not configured.", file=sys.stderr)
        raise SystemExit(1)

    engine = get_postgres_engine()

    # PostgreSQL: new enum values must be committed before use in UPDATE.
    with engine.begin() as conn:
        for value in ENUM_VALUES:
            if dry_run:
                print(f"DRY_RUN enum ADD VALUE {value}")
                continue
            conn.execute(text(f"ALTER TYPE user_role ADD VALUE IF NOT EXISTS '{value}'"))

    if dry_run:
        print(f"DRY_RUN owner -> {owner_email}")
        print(f"DRY_RUN promote_admins={promote_admins}")
        return

    with engine.begin() as conn:
        owner_result = conn.execute(
            text(
                """
                UPDATE users
                SET role = 'owner',
                    email_verified = true,
                    is_active = true,
                    is_banned = false
                WHERE lower(email) = lower(:owner)
                """
            ),
            {"owner": owner_email},
        )
        free_result = conn.execute(
            text("UPDATE users SET role = 'free_user' WHERE role = 'user'")
        )
        promoted = _promote_admins_to_super(conn, owner_email, promote_admins)

    print("PHASE63_ROLE_MIGRATION_OK")
    print(f"owner_rows={int(owner_result.rowcount or 0)}")
    print(f"free_user_rows={int(free_result.rowcount or 0)}")
    print(f"admin_promoted={promoted}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 63 enterprise RBAC migration")
    parser.add_argument("--email", default=os.environ.get("OWNER_EMAIL", DEFAULT_OWNER))
    parser.add_argument(
        "--keep-admin-role",
        action="store_true",
        help="Do not promote admin users to super_admin",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    migrate_roles(
        owner_email=args.email.strip().lower(),
        promote_admins=not args.keep_admin_role,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
