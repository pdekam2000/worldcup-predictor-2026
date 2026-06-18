"""Initial PostgreSQL SaaS schema — Phase 1.

Revision ID: 001_saas_initial
Revises:
Create Date: 2026-06-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_saas_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = postgresql.ENUM("user", "admin", name="user_role", create_type=False)
favorite_type = postgresql.ENUM("team", "league", "match", name="favorite_type", create_type=False)
alert_type = postgresql.ENUM(
    "new_prediction", "high_confidence", "match_result", "system", name="alert_type", create_type=False
)
notification_type = postgresql.ENUM(
    "prediction", "system", "subscription", "accuracy", name="notification_type", create_type=False
)
subscription_plan = postgresql.ENUM("free", "pro", "elite", "unlimited", name="subscription_plan", create_type=False)
billing_cycle = postgresql.ENUM("monthly", "yearly", name="billing_cycle", create_type=False)
subscription_status = postgresql.ENUM(
    "active", "cancelled", "expired", "trial", name="subscription_status", create_type=False
)
prediction_1x2 = postgresql.ENUM("home", "draw", "away", name="prediction_1x2", create_type=False)
prediction_result = postgresql.ENUM("correct", "incorrect", "pending", name="prediction_result", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    favorite_type.create(bind, checkfirst=True)
    alert_type.create(bind, checkfirst=True)
    notification_type.create(bind, checkfirst=True)
    subscription_plan.create(bind, checkfirst=True)
    billing_cycle.create(bind, checkfirst=True)
    subscription_status.create(bind, checkfirst=True)
    prediction_1x2.create(bind, checkfirst=True)
    prediction_result.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("language", sa.String(length=8), server_default="en", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "user_favorites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", favorite_type, nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("item_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "type", "item_id", name="uq_user_favorites_user_type_item"),
    )
    op.create_index("ix_user_favorites_user_id", "user_favorites", ["user_id"], unique=False)

    op.create_table(
        "user_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", alert_type, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_alerts_user_id_created", "user_alerts", ["user_id", "created_at"], unique=False)
    op.create_index("ix_user_alerts_user_unread", "user_alerts", ["user_id", "is_read"], unique=False)

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", notification_type, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=512), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_notifications_user_id_created", "user_notifications", ["user_id", "created_at"], unique=False
    )
    op.create_index("ix_user_notifications_user_unread", "user_notifications", ["user_id", "is_read"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("plan", subscription_plan, server_default="free", nullable=False),
        sa.Column("billing_cycle", billing_cycle, server_default="monthly", nullable=False),
        sa.Column("status", subscription_status, server_default="active", nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("external_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"], unique=False)

    op.create_table(
        "user_prediction_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("prediction_id", sa.String(length=64), nullable=True),
        sa.Column("home_team", sa.String(length=255), nullable=False),
        sa.Column("away_team", sa.String(length=255), nullable=False),
        sa.Column("league", sa.String(length=255), nullable=True),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prediction_1x2", prediction_1x2, nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("result", prediction_result, server_default="pending", nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_prediction_history_user_viewed", "user_prediction_history", ["user_id", "viewed_at"], unique=False
    )
    op.create_index("ix_user_prediction_history_fixture", "user_prediction_history", ["fixture_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_prediction_history_fixture", table_name="user_prediction_history")
    op.drop_index("ix_user_prediction_history_user_viewed", table_name="user_prediction_history")
    op.drop_table("user_prediction_history")

    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_user_notifications_user_unread", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_id_created", table_name="user_notifications")
    op.drop_table("user_notifications")

    op.drop_index("ix_user_alerts_user_unread", table_name="user_alerts")
    op.drop_index("ix_user_alerts_user_id_created", table_name="user_alerts")
    op.drop_table("user_alerts")

    op.drop_index("ix_user_favorites_user_id", table_name="user_favorites")
    op.drop_table("user_favorites")

    op.drop_table("user_settings")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    prediction_result.drop(bind, checkfirst=True)
    prediction_1x2.drop(bind, checkfirst=True)
    subscription_status.drop(bind, checkfirst=True)
    billing_cycle.drop(bind, checkfirst=True)
    subscription_plan.drop(bind, checkfirst=True)
    notification_type.drop(bind, checkfirst=True)
    alert_type.drop(bind, checkfirst=True)
    favorite_type.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
