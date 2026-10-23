"""answer replies to chakshu threads

Revision ID: 9b3e7d41c2a6
Revises: 5d1f0c8a9e21
Create Date: 2026-10-23 16:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b3e7d41c2a6"
down_revision: str | Sequence[str] | None = "5d1f0c8a9e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("reply_to", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "reply_to")
