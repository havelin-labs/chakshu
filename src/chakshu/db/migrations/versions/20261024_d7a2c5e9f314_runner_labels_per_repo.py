"""runner labels per repo

Revision ID: d7a2c5e9f314
Revises: c4e1a7b3d920
Create Date: 2026-10-24 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a2c5e9f314"
down_revision: str | Sequence[str] | None = "c4e1a7b3d920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("repos", sa.Column("runs_on", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("repos", "runs_on")
