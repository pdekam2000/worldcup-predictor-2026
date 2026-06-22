"""Phase 51B — Elite Goal Timing engine tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_goal_timing_engine"
down_revision = "006_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goal_timing_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_key", sa.String(64), nullable=False, server_default="world_cup_2026"),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("source_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_goal_timing_features_fixture_as_of", "goal_timing_features", ["fixture_id", "as_of"])

    op.create_table(
        "goal_timing_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("competition_key", sa.String(64), nullable=False, server_default="world_cup_2026"),
        sa.Column("home_team", sa.String(255), nullable=False),
        sa.Column("away_team", sa.String(255), nullable=False),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("predicted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("first_goal_team", sa.String(16), nullable=False, server_default="none"),
        sa.Column("first_goal_time_range", sa.String(16), nullable=False),
        sa.Column("estimated_first_goal_minute", sa.Numeric(6, 2), nullable=True),
        sa.Column("home_team_goal_probability_by_range", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("away_team_goal_probability_by_range", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("no_goal_before_minute_probability", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("confidence_score", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("data_quality_score", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("specialist_agent_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("no_prediction_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("no_bet_flag", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("goal_timing_features.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_goal_timing_predictions_fixture", "goal_timing_predictions", ["fixture_id"])
    op.create_index("ix_goal_timing_predictions_match_date", "goal_timing_predictions", ["match_date"])

    op.create_table(
        "goal_timing_prediction_markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goal_timing_predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("market_key", sa.String(64), nullable=False),
        sa.Column("predicted_value", sa.String(255), nullable=True),
        sa.Column("probability", sa.Numeric(8, 6), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("prediction_id", "market_key", name="uq_goal_timing_market_per_prediction"),
    )

    op.create_table(
        "goal_timing_agent_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goal_timing_predictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("impact_score", sa.Numeric(6, 4), nullable=True),
        sa.Column("missing_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("prediction_id", "agent_name", name="uq_goal_timing_agent_per_prediction"),
    )

    op.create_table(
        "goal_timing_backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "goal_timing_backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goal_timing_backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("prediction_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("evaluation_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("first_goal_team_correct", sa.Boolean(), nullable=True),
        sa.Column("range_correct", sa.Boolean(), nullable=True),
        sa.Column("minute_error", sa.Numeric(6, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_goal_timing_backtest_results_run", "goal_timing_backtest_results", ["run_id"])

    op.create_table(
        "goal_timing_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goal_timing_predictions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("actual_first_goal_team", sa.String(16), nullable=True),
        sa.Column("actual_first_goal_minute", sa.Integer(), nullable=True),
        sa.Column("actual_first_goal_time_range", sa.String(16), nullable=True),
        sa.Column("first_goal_team_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("time_range_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("minute_tolerance_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_goal_timing_evaluations_fixture", "goal_timing_evaluations", ["fixture_id"])


def downgrade() -> None:
    op.drop_table("goal_timing_evaluations")
    op.drop_table("goal_timing_backtest_results")
    op.drop_table("goal_timing_backtest_runs")
    op.drop_table("goal_timing_agent_outputs")
    op.drop_table("goal_timing_prediction_markets")
    op.drop_table("goal_timing_predictions")
    op.drop_table("goal_timing_features")
