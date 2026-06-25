"""Phase 38A — add starter to subscription_plan enum."""

from alembic import op

revision = "003_starter_plan"
down_revision = "002_super_admin_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE subscription_plan ADD VALUE IF NOT EXISTS 'starter'")


def downgrade() -> None:
    pass
