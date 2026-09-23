"""Trusted faces

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-23

Only a face somebody assigned by hand could vouch for an automatic assignment, so Muninn could
never build on its own correct work: everything ended up as a suggestion waiting to be answered.
A face the machine assigned may vouch too now, but only when it lay very close to one that was
confirmed. This marks those.

Nothing is filled here. The next look at the faces decides which of them are trusted, with the
distance it measures itself.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "faces",
        sa.Column("trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("faces", "trusted")
