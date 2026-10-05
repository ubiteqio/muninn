"""The hour the duplicates are found

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-05

Finding the groups of copies reads every medium and rewrites every group. Every quarter of an
hour that kept the NAS at full load for minutes at a time; it now runs once a night, at an hour
the admin chooses.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("duplicates_hour", sa.SmallInteger(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("settings", "duplicates_hour")
