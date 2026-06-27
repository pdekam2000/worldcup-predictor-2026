"""Phase 39B-1 — Stripe billing foundation (subscriptions extension + invoices + webhooks)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_stripe_billing_foundation"
down_revision = "003_starter_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("external_customer_id", sa.String(length=255), nullable=True))
    op.add_column("subscriptions", sa.Column("external_price_id", sa.String(length=255), nullable=True))
    op.add_column("subscriptions", sa.Column("billing_status", sa.String(length=64), nullable=True))
    op.add_column("subscriptions", sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "subscriptions",
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("subscriptions", sa.Column("last_payment_status", sa.String(length=32), nullable=True))
    op.add_column("subscriptions", sa.Column("last_payment_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("billing_updated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_subscriptions_external_customer_id", "subscriptions", ["external_customer_id"], unique=False)
    op.create_index(
        "ix_subscriptions_external_subscription_id", "subscriptions", ["external_subscription_id"], unique=False
    )
    op.create_index("ix_subscriptions_billing_status", "subscriptions", ["billing_status"], unique=False)

    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("external_invoice_id", sa.String(length=255), nullable=False),
        sa.Column("external_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("amount_due", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("amount_paid", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("invoice_url", sa.String(length=512), nullable=True),
        sa.Column("hosted_invoice_url", sa.String(length=512), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_invoice_id", name="uq_billing_invoices_external_invoice_id"),
    )
    op.create_index("ix_billing_invoices_user_id", "billing_invoices", ["user_id"], unique=False)
    op.create_index("ix_billing_invoices_subscription_id", "billing_invoices", ["subscription_id"], unique=False)

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=True),
        sa.Column("api_version", sa.String(length=32), nullable=True),
        sa.Column("livemode", sa.Boolean(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_webhook_events_stripe_event_id"),
    )
    op.create_index("ix_stripe_webhook_events_event_type", "stripe_webhook_events", ["event_type"], unique=False)
    op.create_index("ix_stripe_webhook_events_processed", "stripe_webhook_events", ["processed"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stripe_webhook_events_processed", table_name="stripe_webhook_events")
    op.drop_index("ix_stripe_webhook_events_event_type", table_name="stripe_webhook_events")
    op.drop_table("stripe_webhook_events")

    op.drop_index("ix_billing_invoices_subscription_id", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_user_id", table_name="billing_invoices")
    op.drop_table("billing_invoices")

    op.drop_index("ix_subscriptions_billing_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_external_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_external_customer_id", table_name="subscriptions")

    op.drop_column("subscriptions", "billing_updated_at")
    op.drop_column("subscriptions", "last_payment_at")
    op.drop_column("subscriptions", "last_payment_status")
    op.drop_column("subscriptions", "cancel_at_period_end")
    op.drop_column("subscriptions", "current_period_end")
    op.drop_column("subscriptions", "current_period_start")
    op.drop_column("subscriptions", "billing_status")
    op.drop_column("subscriptions", "external_price_id")
    op.drop_column("subscriptions", "external_customer_id")
