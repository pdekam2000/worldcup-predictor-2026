"""Validate Phase 1 PostgreSQL foundation (imports + optional live DB)."""

from __future__ import annotations

import sys


def main() -> int:
    errors: list[str] = []

    try:
        from worldcup_predictor.database.postgres import Base, models  # noqa: F401
        from worldcup_predictor.database.postgres.models import (  # noqa: F401
            Subscription,
            User,
            UserAlert,
            UserFavorite,
            UserNotification,
            UserPredictionHistory,
            UserSettings,
        )
        from worldcup_predictor.database.saas_factory import saas_uow
        from worldcup_predictor.config.settings import get_settings

        tables = sorted(Base.metadata.tables.keys())
        expected = {
            "users",
            "user_settings",
            "user_favorites",
            "user_alerts",
            "user_notifications",
            "subscriptions",
            "user_prediction_history",
        }
        missing = expected - set(tables)
        if missing:
            errors.append(f"Missing tables in metadata: {missing}")
        print(f"OK: {len(tables)} tables registered — {', '.join(tables)}")

        settings = get_settings()
        if settings.postgres_configured:
            from worldcup_predictor.database.postgres.session import ping_postgres

            if ping_postgres():
                print("OK: PostgreSQL ping")
            else:
                print("WARN: DATABASE_URL set but ping failed (is PostgreSQL running?)")
        else:
            print("SKIP: DATABASE_URL not set — migration not tested")

    except Exception as exc:
        errors.append(str(exc))

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
