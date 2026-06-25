"""Phase 39A — commercial analytics for Super Admin (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.enums import SubscriptionPlan
from worldcup_predictor.database.postgres.models import Subscription, User
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.subscription.plan_limits import normalize_plan


def _sqlite_conn(settings: Settings | None = None):
    settings = settings or get_settings()
    return FootballIntelligenceRepository(settings.sqlite_path or None)._conn


def count_contact_messages(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    conn = _sqlite_conn(settings)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_contact_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                email_sent INTEGER NOT NULL DEFAULT 0,
                category TEXT DEFAULT 'other'
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) AS c FROM admin_contact_messages").fetchone()
        return int(row["c"]) if row else 0
    except Exception:
        return 0


def count_monthly_prediction_usage(settings: Settings | None = None) -> int:
    """Total successful prediction usage records in the current UTC month."""
    settings = settings or get_settings()
    conn = _sqlite_conn(settings)
    prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_prediction_usage (
                user_id TEXT NOT NULL,
                billing_period TEXT NOT NULL,
                fixture_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, billing_period, fixture_id)
            )
            """
        )
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM user_prediction_usage WHERE created_at LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        return int(row["c"]) if row else 0
    except Exception:
        return 0


def build_commercial_analytics(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    plan_counts = {"free": 0, "starter": 0, "pro": 0}
    total_users = 0

    try:
        with saas_uow() as uow:
            session = uow.session
            total_users = int(session.scalar(select(func.count()).select_from(User)) or 0)
            rows = session.execute(select(Subscription.plan, func.count()).group_by(Subscription.plan)).all()
            for plan, count in rows:
                key = normalize_plan(plan.value if hasattr(plan, "value") else str(plan))
                plan_counts[key] = plan_counts.get(key, 0) + int(count)
            # Users without subscription row count as free
            sub_total = sum(plan_counts.values())
            if sub_total < total_users:
                plan_counts["free"] += total_users - sub_total
    except Exception:
        pass

    return {
        "total_users": total_users,
        "free_users": plan_counts.get("free", 0),
        "starter_users": plan_counts.get("starter", 0),
        "pro_users": plan_counts.get("pro", 0),
        "paid_users": plan_counts.get("starter", 0) + plan_counts.get("pro", 0),
        "monthly_prediction_usage": count_monthly_prediction_usage(settings),
        "contact_messages_count": count_contact_messages(settings),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
