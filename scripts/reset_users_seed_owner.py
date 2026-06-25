#!/usr/bin/env python3
"""Phase 40A — safe user database reset and owner seed.

Requires --confirm-reset-users. Never hardcodes passwords.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from worldcup_predictor.access.admin_gate import write_admin_audit_event
from worldcup_predictor.auth.passwords import hash_password
from worldcup_predictor.api.web_auth import seed_owner_account
from worldcup_predictor.database.postgres.enums import SubscriptionPlan
from worldcup_predictor.database.saas_factory import postgres_configured, saas_uow

OWNER_EMAIL = "kamangar.pedram@gmail.com"
BACKUP_TABLES = (
    "users",
    "user_settings",
    "subscriptions",
    "user_favorites",
    "user_alerts",
    "user_notifications",
    "user_prediction_history",
    "email_verification_tokens",
    "password_reset_tokens",
)


def _backup_dir(root: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = root / "data" / "backups" / f"user_reset_{ts}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _export_table_backup(backup: Path) -> None:
    from sqlalchemy import text

    manifest: dict[str, int] = {}
    with saas_uow() as uow:
        session = uow.session
        for table in BACKUP_TABLES:
            try:
                rows = session.execute(text(f"SELECT row_to_json(t) FROM {table} AS t")).fetchall()
            except Exception:
                continue
            payload = [row[0] for row in rows]
            out = backup / f"{table}.json"
            out.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
            manifest[table] = len(payload)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _resolve_password() -> str:
    env_pwd = (os.environ.get("OWNER_INITIAL_PASSWORD") or "").strip()
    if env_pwd:
        return env_pwd
    pwd = getpass.getpass("Owner initial password: ")
    confirm = getpass.getpass("Confirm password: ")
    if pwd != confirm:
        raise SystemExit("Passwords do not match.")
    if len(pwd) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    return pwd


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset SaaS users and seed owner super_admin.")
    parser.add_argument(
        "--confirm-reset-users",
        action="store_true",
        help="Required flag to perform destructive user reset.",
    )
    parser.add_argument("--email", default=OWNER_EMAIL, help="Owner email to seed.")
    parser.add_argument("--plan", default="pro", choices=["free", "starter", "pro", "elite", "unlimited"])
    args = parser.parse_args()

    if not args.confirm_reset_users:
        print("Refusing reset: pass --confirm-reset-users to proceed.")
        return 1

    if not postgres_configured():
        print("PostgreSQL DATABASE_URL is not configured.")
        return 1

    root = Path(__file__).resolve().parents[1]
    backup = _backup_dir(root)
    print(f"Backing up user-related tables to {backup} ...")
    _export_table_backup(backup)

    deleted = 0
    with saas_uow() as uow:
        deleted = uow.users.delete_all_users()
    print(f"Deleted {deleted} user(s).")

    password = _resolve_password()
    record = seed_owner_account(
        email=args.email.strip().lower(),
        password_hash=hash_password(password),
        full_name=args.email.split("@")[0],
        plan=SubscriptionPlan(args.plan),
    )
    write_admin_audit_event(
        "owner_seeded",
        user_id=str(record.id),
        detail=f"email={record.email};plan={args.plan}",
    )
    write_admin_audit_event("user_reset_performed", detail=f"deleted={deleted};backup={backup}")

    print("Owner seeded:")
    print(json.dumps({
        "id": str(record.id),
        "email": record.email,
        "role": record.role.value,
        "email_verified": record.email_verified,
        "plan": args.plan,
        "backup": str(backup),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
