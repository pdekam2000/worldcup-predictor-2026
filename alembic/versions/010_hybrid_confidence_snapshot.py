"""Phase 52E — hybrid confidence snapshot on goal timing predictions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_hybrid_confidence_snapshot"
down_revision = "009_goal_timing_display_minutes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "goal_timing_predictions",
        sa.Column("hybrid_confidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("goal_timing_predictions", "hybrid_confidence_snapshot")
