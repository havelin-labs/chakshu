"""github teams and dated memberships

Revision ID: 9b2d6e4f8a13
Revises: 7f3c9a1d5e42
Create Date: 2026-10-24 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b2d6e4f8a13"
down_revision: str | Sequence[str] | None = "7f3c9a1d5e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "github_teams",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("org", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installations.id"],
            name=op.f("fk_github_teams_installation_id_installations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_github_teams")),
    )
    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("login_lower", sa.String(length=100), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["github_teams.id"],
            name=op.f("fk_team_memberships_team_id_github_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_memberships")),
    )
    op.create_index(
        "uq_team_memberships_open",
        "team_memberships",
        ["team_id", "login_lower"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index("ix_team_memberships_login_lower", "team_memberships", ["login_lower", "team_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_team_memberships_login_lower", table_name="team_memberships")
    op.drop_index("uq_team_memberships_open", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_table("github_teams")
