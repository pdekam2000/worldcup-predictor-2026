#!/usr/bin/env python3
"""Phase 62 — ensure owner super_admin account exists with correct flags (no password change)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from worldcup_predictor.database.postgres.enums import SubscriptionPlan, UserRole
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

DEFAULT_EMAIL = "kamangar.pedram@gmail.com"


def ensure_owner_super_admin(*, email: str, preserve_plan: bool = True) -> None:
    normalized = email.strip().lower()

    with saas_uow() as uow:
        existing = uow.users.get_by_email(normalized)
        if existing is None:
            print(
                f"Owner account not found: {normalized}. "
                "Run scripts/reset_owner_login_password.py with OWNER_LOGIN_PASSWORD set.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        uow.users.set_email_verified(existing.id, True)
        uow.users.clear_ban(existing.id)
        uow.users.set_active(existing.id, True)
        uow.users.set_role(existing.id, UserRole.SUPER_ADMIN)
        uow.settings.get_or_create(existing.id)

        if not preserve_plan:
            uow.subscriptions.upsert(existing.id, plan=SubscriptionPlan.PRO)

        updated = uow.users.get_by_id(existing.id)

    if updated is None:
        print("Failed to load owner after update.", file=sys.stderr)
        raise SystemExit(1)

    role = updated.role.value if hasattr(updated.role, "value") else str(updated.role)
    print("OWNER_SUPER_ADMIN_OK")
    print(updated.email)
    print(role)
    print(str(updated.email_verified).lower())
    print(str(updated.is_active).lower())
    print(str(updated.is_banned).lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure owner has super_admin role (Phase 62).")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Owner email.")
    parser.add_argument(
        "--force-pro-plan",
        action="store_true",
        help="Upsert PRO plan (default: preserve existing subscription).",
    )
    args = parser.parse_args()

    if not postgres_configured():
        print("PostgreSQL DATABASE_URL is not configured.", file=sys.stderr)
        return 1

    ensure_owner_super_admin(email=args.email, preserve_plan=not args.force_pro_plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
