"""analytics foundations

Revision ID: c71a4e2b9d05
Revises: 9b3e7d41c2a6
Create Date: 2026-10-23 16:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c71a4e2b9d05"
down_revision: str | Sequence[str] | None = "9b3e7d41c2a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("pr_author", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_runs_pr_author"), "runs", ["pr_author"], unique=False)
    op.create_index("ix_runs_created_at_repo_id", "runs", ["created_at", "repo_id"], unique=False)
    op.add_column("posted_findings", sa.Column("outcome_source", sa.String(length=20), nullable=True))
    op.create_table(
        "analytics_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_login", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("view", sa.String(length=50), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_audit")),
    )
    op.create_index(op.f("ix_analytics_audit_created_at"), "analytics_audit", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_analytics_audit_created_at"), table_name="analytics_audit")
    op.drop_table("analytics_audit")
    op.drop_column("posted_findings", "outcome_source")
    op.drop_index("ix_runs_created_at_repo_id", table_name="runs")
    op.drop_index(op.f("ix_runs_pr_author"), table_name="runs")
    op.drop_column("runs", "pr_author")
