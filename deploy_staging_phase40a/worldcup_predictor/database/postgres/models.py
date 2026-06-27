"""PostgreSQL ORM models — SaaS production tables (Phase 1).

Intelligence/prediction tables remain in SQLite until a later phase.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from worldcup_predictor.database.postgres.base import Base
from worldcup_predictor.database.postgres.enums import (
    AlertType,
    BillingCycle,
    FavoriteType,
    NotificationType,
    Prediction1x2,
    PredictionResult,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)


def _pg_enum(enum_cls: type, name: str) -> SAEnum:
    """Bind Python enums by value (e.g. 'user') not name ('USER')."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [member.value for member in members],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        _pg_enum(UserRole, "user_role"),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    settings: Mapped["UserSettings | None"] = relationship(back_populates="user", uselist=False)
    favorites: Mapped[list["UserFavorite"]] = relationship(back_populates="user")
    alerts: Mapped[list["UserAlert"]] = relationship(back_populates="user")
    notifications: Mapped[list["UserNotification"]] = relationship(back_populates="user")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="user", uselist=False)
    prediction_history: Mapped[list["UserPredictionHistory"]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_role", "role"),)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_email_verification_tokens_user_id", "user_id"),
        Index("ix_email_verification_tokens_token_hash", "token_hash"),
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en", server_default="en")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="settings")


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[FavoriteType] = mapped_column(_pg_enum(FavoriteType, "favorite_type"), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "type", "item_id", name="uq_user_favorites_user_type_item"),
        Index("ix_user_favorites_user_id", "user_id"),
    )


class UserAlert(Base):
    __tablename__ = "user_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[AlertType] = mapped_column(_pg_enum(AlertType, "alert_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="alerts")

    __table_args__ = (
        Index("ix_user_alerts_user_id_created", "user_id", "created_at"),
        Index("ix_user_alerts_user_unread", "user_id", "is_read"),
    )


class UserNotification(Base):
    __tablename__ = "user_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(_pg_enum(NotificationType, "notification_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_user_notifications_user_id_created", "user_id", "created_at"),
        Index("ix_user_notifications_user_unread", "user_id", "is_read"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan: Mapped[SubscriptionPlan] = mapped_column(
        _pg_enum(SubscriptionPlan, "subscription_plan"),
        nullable=False,
        default=SubscriptionPlan.FREE,
        server_default=SubscriptionPlan.FREE.value,
    )
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        _pg_enum(BillingCycle, "billing_cycle"),
        nullable=False,
        default=BillingCycle.MONTHLY,
        server_default=BillingCycle.MONTHLY.value,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        _pg_enum(SubscriptionStatus, "subscription_status"),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
        server_default=SubscriptionStatus.ACTIVE.value,
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Phase 39B-1 — Stripe billing foundation
    external_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_payment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="subscription")
    billing_invoices: Mapped[list["BillingInvoice"]] = relationship(back_populates="subscription")

    __table_args__ = (
        Index("ix_subscriptions_status", "status"),
        Index("ix_subscriptions_external_customer_id", "external_customer_id"),
        Index("ix_subscriptions_external_subscription_id", "external_subscription_id"),
        Index("ix_subscriptions_billing_status", "billing_status"),
    )


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_invoice_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_due: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hosted_invoice_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    subscription: Mapped["Subscription | None"] = relationship(back_populates="billing_invoices")

    __table_args__ = (
        UniqueConstraint("external_invoice_id", name="uq_billing_invoices_external_invoice_id"),
        Index("ix_billing_invoices_user_id", "user_id"),
        Index("ix_billing_invoices_subscription_id", "subscription_id"),
    )


class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    livemode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("stripe_event_id", name="uq_stripe_webhook_events_stripe_event_id"),
        Index("ix_stripe_webhook_events_event_type", "event_type"),
        Index("ix_stripe_webhook_events_processed", "processed"),
    )


class UserPredictionHistory(Base):
    __tablename__ = "user_prediction_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prediction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    home_team: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team: Mapped[str] = mapped_column(String(255), nullable=False)
    league: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prediction_1x2: Mapped[Prediction1x2] = mapped_column(
        _pg_enum(Prediction1x2, "prediction_1x2"),
        nullable=False,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    result: Mapped[PredictionResult] = mapped_column(
        _pg_enum(PredictionResult, "prediction_result"),
        nullable=False,
        default=PredictionResult.PENDING,
        server_default=PredictionResult.PENDING.value,
    )
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="prediction_history")

    __table_args__ = (
        Index("ix_user_prediction_history_user_viewed", "user_id", "viewed_at"),
        Index("ix_user_prediction_history_fixture", "fixture_id"),
    )
