"""Phase 54J — Player lineup / match-stat feature store (PostgreSQL intelligence layer)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013_player_feature_store"
down_revision = "012_pressure_feature_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fs_player_match_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("player_name", sa.String(256), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.String(16), nullable=True),
        sa.Column("starter", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("captain", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shots_on_target", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating", sa.Numeric(6, 3), nullable=True),
        sa.Column("xg", sa.Numeric(10, 4), nullable=True),
        sa.Column("xa", sa.Numeric(10, 4), nullable=True),
        sa.Column("yellow_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("red_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="sportmonks_cache"),
        sa.Column("raw_reference", sa.String(512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("sportmonks_fixture_id", "player_id", name="uq_fs_player_match_fixture_player"),
    )
    op.create_index("ix_fs_player_match_fixture", "fs_player_match_stats", ["sportmonks_fixture_id"])
    op.create_index("ix_fs_player_match_player", "fs_player_match_stats", ["player_id", "match_date"])
    op.create_index("ix_fs_player_match_league_season", "fs_player_match_stats", ["league_id", "season_id"])
    op.create_index("ix_fs_player_match_team", "fs_player_match_stats", ["team_id"])

    op.create_table(
        "fs_player_rolling_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=True),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("goals_last_3", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_last_5", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_last_10", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists_last_5", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minutes_last_5", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("starts_last_5", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shots_last_5", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shots_on_target_last_5", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xg_last_5", sa.Numeric(10, 4), nullable=True),
        sa.Column("xg_last_10", sa.Numeric(10, 4), nullable=True),
        sa.Column("goals_per_90", sa.Numeric(10, 4), nullable=True),
        sa.Column("xg_per_90", sa.Numeric(10, 4), nullable=True),
        sa.Column("starter_probability", sa.Numeric(6, 4), nullable=True),
        sa.Column("recent_form_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("starter", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("captain", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("position", sa.String(16), nullable=True),
        sa.Column("position_group", sa.String(16), nullable=True),
        sa.Column("formation", sa.String(32), nullable=True),
        sa.Column("goalkeeper_player_id", sa.BigInteger(), nullable=True),
        sa.Column("captain_player_id", sa.BigInteger(), nullable=True),
        sa.Column("lineup_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("lineup_quality_score", sa.Numeric(6, 3), nullable=True),
        sa.Column(
            "starting_xi_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "bench_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("source", sa.String(32), nullable=False, server_default="sportmonks_cache"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("sportmonks_fixture_id", "player_id", name="uq_fs_player_rolling_fixture_player"),
    )
    op.create_index("ix_fs_player_rolling_fixture", "fs_player_rolling_features", ["sportmonks_fixture_id"])
    op.create_index("ix_fs_player_rolling_player", "fs_player_rolling_features", ["player_id", "match_date"])
    op.create_index("ix_fs_player_rolling_league", "fs_player_rolling_features", ["league_id", "season_id"])

    op.create_table(
        "fs_player_ingest_manifest",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_key", sa.String(64), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("sportmonks_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("player_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rolling_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_key", "sportmonks_fixture_id", name="uq_fs_player_ingest_job_fixture"),
    )
    op.create_index("ix_fs_player_ingest_job", "fs_player_ingest_manifest", ["job_key", "status"])


def downgrade() -> None:
    op.drop_table("fs_player_ingest_manifest")
    op.drop_table("fs_player_rolling_features")
    op.drop_table("fs_player_match_stats")
