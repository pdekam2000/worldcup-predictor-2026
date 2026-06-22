"""EGIE Phase 1A — PostgreSQL raw provider store and ingest run audit."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_egie_provider_raw_store"
down_revision = "007_goal_timing_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "egie_provider_raw_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("competition_key", sa.String(64), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("request_endpoint", sa.String(128), nullable=False),
        sa.Column(
            "request_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("payload_hash", sa.String(64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="live"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider", "request_fingerprint", name="uq_egie_raw_provider_fingerprint"),
    )
    op.create_index(
        "ix_egie_raw_fixture_resource",
        "egie_provider_raw_responses",
        ["fixture_id", "resource_type"],
    )
    op.create_index(
        "ix_egie_raw_competition_season",
        "egie_provider_raw_responses",
        ["competition_key", "season", "resource_type"],
    )
    op.create_index(
        "ix_egie_raw_sportmonks_fixture",
        "egie_provider_raw_responses",
        ["sportmonks_fixture_id", "resource_type"],
    )

    op.create_table(
        "egie_ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("competition_key", sa.String(64), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_egie_ingest_runs_job", "egie_ingest_runs", ["job_key", "started_at"])


def downgrade() -> None:
    op.drop_table("egie_ingest_runs")
    op.drop_table("egie_provider_raw_responses")
