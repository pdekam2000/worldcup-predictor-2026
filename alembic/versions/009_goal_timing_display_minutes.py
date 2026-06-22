"""Phase 51D+ — goal timing prediction display minute columns."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_goal_timing_display_minutes"
down_revision = "008_egie_provider_raw_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "goal_timing_predictions",
        sa.Column("display_estimated_first_goal_minute", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "goal_timing_predictions",
        sa.Column("bucket_representative_minute", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "goal_timing_predictions",
        sa.Column("weighted_average_minute", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "goal_timing_predictions",
        sa.Column("model_confidence_score", sa.Numeric(6, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("goal_timing_predictions", "model_confidence_score")
    op.drop_column("goal_timing_predictions", "weighted_average_minute")
    op.drop_column("goal_timing_predictions", "bucket_representative_minute")
    op.drop_column("goal_timing_predictions", "display_estimated_first_goal_minute")
