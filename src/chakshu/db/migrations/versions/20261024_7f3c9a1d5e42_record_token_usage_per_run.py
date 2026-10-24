"""record token usage per run

Revision ID: 7f3c9a1d5e42
Revises: 4e8a2f6b1c37
Create Date: 2026-10-24 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3c9a1d5e42"
down_revision: str | Sequence[str] | None = "4e8a2f6b1c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def upgrade() -> None:
    """Upgrade schema."""
    for name in COLUMNS:
        op.add_column("runs", sa.Column(name, sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for name in reversed(COLUMNS):
        op.drop_column("runs", name)
