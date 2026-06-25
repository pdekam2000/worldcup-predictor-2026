"""Phase 54H — Sportmonks Pressure feature store (PostgreSQL intelligence layer)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012_pressure_feature_store"
down_revision = "011_sportmonks_xg_feature_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fs_sportmonks_pressure_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("pressure_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("pressure_row_id", sa.BigInteger(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="sportmonks_fixture"),
        sa.Column("raw_reference", sa.String(512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "sportmonks_fixture_id",
            "pressure_row_id",
            name="uq_fs_pressure_row_identity",
        ),
    )
    op.create_index("ix_fs_pressure_fixture", "fs_sportmonks_pressure_records", ["sportmonks_fixture_id"])
    op.create_index("ix_fs_pressure_league_season", "fs_sportmonks_pressure_records", ["league_id", "season_id"])
    op.create_index("ix_fs_pressure_participant_minute", "fs_sportmonks_pressure_records", ["participant_id", "minute"])
    op.create_index("ix_fs_pressure_fixture_minute", "fs_sportmonks_pressure_records", ["sportmonks_fixture_id", "minute"])

    op.create_table(
        "fs_sportmonks_pressure_fixture_summary",
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), primary_key=True),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("home_team_id", sa.Integer(), nullable=True),
        sa.Column("away_team_id", sa.Integer(), nullable=True),
        sa.Column("match_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pressure_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_goal_minute", sa.Integer(), nullable=True),
        sa.Column(
            "features_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="sportmonks_fixture"),
    )
    op.create_index("ix_fs_pressure_summary_league", "fs_sportmonks_pressure_fixture_summary", ["league_id", "season_id"])
    op.create_index("ix_fs_pressure_summary_teams", "fs_sportmonks_pressure_fixture_summary", ["home_team_id", "away_team_id"])

    op.create_table(
        "fs_sportmonks_pressure_ingest_manifest",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_key", sa.String(64), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("api_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_key", "sportmonks_fixture_id", name="uq_fs_pressure_ingest_job_fixture"),
    )
    op.create_index("ix_fs_pressure_ingest_job", "fs_sportmonks_pressure_ingest_manifest", ["job_key", "status"])


def downgrade() -> None:
    op.drop_table("fs_sportmonks_pressure_ingest_manifest")
    op.drop_table("fs_sportmonks_pressure_fixture_summary")
    op.drop_table("fs_sportmonks_pressure_records")
