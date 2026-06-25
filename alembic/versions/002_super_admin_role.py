"""Phase 37A — add super_admin to userrole enum."""

from alembic import op

revision = "002_super_admin_role"
down_revision = "001_saas_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'super_admin'")


def downgrade() -> None:
    # PostgreSQL enums cannot drop values safely; no-op downgrade.
    pass
