"""pr events for review speed

Revision ID: c4e1a7b3d920
Revises: 9b2d6e4f8a13
Create Date: 2026-10-24 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e1a7b3d920"
down_revision: str | Sequence[str] | None = "9b2d6e4f8a13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pr_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"], ["repos.id"], name=op.f("fk_pr_events_repo_id_repos"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pr_events")),
    )
    op.create_index("uq_pr_events_pr_kind", "pr_events", ["repo_id", "pr_number", "kind"], unique=True)
    op.create_index(op.f("ix_pr_events_at"), "pr_events", ["at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_pr_events_at"), table_name="pr_events")
    op.drop_index("uq_pr_events_pr_kind", table_name="pr_events")
    op.drop_table("pr_events")
