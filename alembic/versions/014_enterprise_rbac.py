"""Phase 63 — enterprise RBAC enum expansion + safe role data migration."""

from alembic import op

revision = "014_enterprise_rbac"
down_revision = "013_player_feature_store"
branch_labels = None
depends_on = None

_NEW_VALUES = (
    "guest",
    "free_user",
    "starter",
    "pro",
    "premium",
    "owner",
)

_OWNER_EMAIL = "kamangar.pedram@gmail.com"


def upgrade() -> None:
    # super_admin may already exist from 002; IF NOT EXISTS is safe.
    for value in ("super_admin", *_NEW_VALUES):
        op.execute(f"ALTER TYPE user_role ADD VALUE IF NOT EXISTS '{value}'")

    # Promote platform owner (never deletes users).
    op.execute(
        f"""
        UPDATE users
        SET role = 'owner'
        WHERE lower(email) = lower('{_OWNER_EMAIL}')
        """
    )

    # Existing admins → super_admin (preserves privilege; reversible in downgrade script).
    op.execute(
        """
        UPDATE users
        SET role = 'super_admin'
        WHERE role = 'admin'
          AND lower(email) <> lower('"""
        + _OWNER_EMAIL
        + """')
        """
    )

    # Legacy user → free_user label (same privilege tier).
    op.execute(
        """
        UPDATE users
        SET role = 'free_user'
        WHERE role = 'user'
        """
    )


def downgrade() -> None:
    # Reversible data mapping only — PostgreSQL cannot drop enum values.
    op.execute(
        f"""
        UPDATE users
        SET role = 'super_admin'
        WHERE lower(email) = lower('{_OWNER_EMAIL}')
        """
    )
    op.execute(
        """
        UPDATE users
        SET role = 'admin'
        WHERE role = 'super_admin'
        """
    )
    op.execute(
        """
        UPDATE users
        SET role = 'user'
        WHERE role = 'free_user'
        """
    )
