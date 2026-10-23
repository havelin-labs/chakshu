"""run reviews in github actions

Revision ID: 5d1f0c8a9e21
Revises: bd965417f7d9
Create Date: 2026-10-23 10:12:40.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d1f0c8a9e21"
down_revision: str | Sequence[str] | None = "bd965417f7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("actions_run_id", sa.BigInteger(), nullable=True))
    op.add_column("runs", sa.Column("actions_run_url", sa.String(length=500), nullable=True))
    op.create_index(op.f("ix_runs_actions_run_id"), "runs", ["actions_run_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_runs_actions_run_id"), table_name="runs")
    op.drop_column("runs", "actions_run_url")
    op.drop_column("runs", "actions_run_id")
