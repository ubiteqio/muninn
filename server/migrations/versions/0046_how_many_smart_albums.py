"""How many smart albums there are

Revision ID: 0046
Revises: 0045
Create Date: 2026-09-26

An admin says two things about the Smarts: how many there are and how much each one holds. The
second was already a setting; this is the first. What the number means is plain - the chapters
are cut to it after the kinds have taken turns, so what is left is still a mixture.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("smart_max_chapters", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("settings", "smart_max_chapters")
