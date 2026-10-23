"""people directory

Revision ID: 4e8a2f6b1c37
Revises: c71a4e2b9d05
Create Date: 2026-10-23 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e8a2f6b1c37"
down_revision: str | Sequence[str] | None = "c71a4e2b9d05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "org_members",
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("login_lower", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("org_role", sa.String(length=10), nullable=False),
        sa.Column("in_org", sa.Boolean(), nullable=False),
        sa.Column("name_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("login", name=op.f("pk_org_members")),
        sa.UniqueConstraint("login_lower", name=op.f("uq_org_members_login_lower")),
    )
    op.add_column("analytics_audit", sa.Column("target_login", sa.String(length=100), nullable=True))
    op.alter_column(
        "analytics_audit", "action", type_=sa.String(length=50), existing_type=sa.String(length=20)
    )
    op.create_index(
        "ix_runs_lower_requested_by_created_at", "runs", [sa.text("lower(requested_by)"), "created_at"]
    )
    op.create_index("ix_runs_lower_pr_author_created_at", "runs", [sa.text("lower(pr_author)"), "created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_runs_lower_pr_author_created_at", table_name="runs")
    op.drop_index("ix_runs_lower_requested_by_created_at", table_name="runs")
    op.alter_column(
        "analytics_audit", "action", type_=sa.String(length=20), existing_type=sa.String(length=50)
    )
    op.drop_column("analytics_audit", "target_login")
    op.drop_table("org_members")
