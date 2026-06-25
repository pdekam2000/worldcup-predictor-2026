#!/usr/bin/env python3
"""Phase 41C — safe single-user owner password reset (no mass reset, no plaintext in DB/logs)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from worldcup_predictor.api.web_auth import seed_owner_account
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
from worldcup_predictor.database.postgres.session import get_postgres_engine
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

MIN_PASSWORD_LENGTH = 8
DEFAULT_EMAIL = "kamangar.pedram@gmail.com"


def _resolve_password(env_name: str) -> str:
    pwd = (os.environ.get(env_name) or "").strip()
    if not pwd:
        print(f"Missing password: set {env_name} in the environment.", file=sys.stderr)
        raise SystemExit(1)
    if len(pwd) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        raise SystemExit(1)
    return pwd


def _reset_owner_password_sql(*, email: str, password_hash: str) -> dict:
    from sqlalchemy import text

    engine = get_postgres_engine()
    with engine.begin() as conn:
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
            {"email": email, "pwd": password_hash},
        )
        row = conn.execute(
            text(
                """
                SELECT email, role::text, email_verified, is_active, is_banned
                FROM users WHERE lower(email) = lower(:email)
                """
            ),
            {"email": email},
        ).fetchone()
    if row is None:
        raise SystemExit("Password reset failed: user not found after SQL update.")
    return {
        "email": row[0],
        "role": row[1],
        "email_verified": bool(row[2]),
        "is_active": bool(row[3]),
        "is_banned": bool(row[4]),
    }


def reset_owner_password(*, email: str, password: str) -> None:
    normalized = email.strip().lower()
    pwd_hash = hash_password(password)

    try:
        with saas_uow() as uow:
            existing = uow.users.get_by_email(normalized)
            if existing is None:
                record = seed_owner_account(
                    email=normalized,
                    password_hash=pwd_hash,
                    full_name=normalized.split("@")[0],
                    plan=SubscriptionPlan.PRO,
                )
                with saas_uow() as uow2:
                    if hasattr(uow2.users, "bump_token_version"):
                        uow2.users.bump_token_version(record.id)
                    updated = uow2.users.get_by_id(record.id)
            else:
                uow.users.update_password_hash(existing.id, pwd_hash)
                if hasattr(uow.users, "set_email_verified"):
                    uow.users.set_email_verified(existing.id, True)
                    uow.users.clear_ban(existing.id)
                    uow.users.set_active(existing.id, True)
                    uow.users.set_role(existing.id, UserRole.OWNER)
                    uow.users.bump_token_version(existing.id)
                else:
                    raise AttributeError("legacy user repository")
                uow.subscriptions.upsert(existing.id, plan=SubscriptionPlan.PRO)
                updated = uow.users.get_by_id(existing.id)
    except AttributeError:
        info = _reset_owner_password_sql(email=normalized, password_hash=pwd_hash)
        print("PASSWORD_RESET_OK")
        print(info["email"])
        print(info["role"])
        print(str(info["email_verified"]).lower())
        print(str(info["is_active"]).lower())
        print(str(info["is_banned"]).lower())
        return

    if updated is None:
        print("Password reset failed: user not available after update.", file=sys.stderr)
        raise SystemExit(1)

    role = updated.role.value if hasattr(updated.role, "value") else str(updated.role)
    print("PASSWORD_RESET_OK")
    print(updated.email)
    print(role)
    print(str(updated.email_verified).lower())
    print(str(updated.is_active).lower())
    print(str(updated.is_banned).lower())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset password for a single owner/super_admin account (Phase 41C)."
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Owner email to reset.")
    parser.add_argument(
        "--password-env",
        default="OWNER_LOGIN_PASSWORD",
        help="Environment variable holding the new password (never printed).",
    )
    args = parser.parse_args()

    if not postgres_configured():
        print("PostgreSQL DATABASE_URL is not configured.", file=sys.stderr)
        return 1

    password = _resolve_password(args.password_env)
    reset_owner_password(email=args.email, password=password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
