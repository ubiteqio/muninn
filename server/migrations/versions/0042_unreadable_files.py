"""Files the reading had to walk past

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-24

A file that could not be opened took the whole reading down with it. Every pass died on the
same file, no other file anywhere was confirmed again, and the only trace was a traceback in a
worker's log - so thirty-three files in unrelated folders sat waiting with nothing to say why.

Such a file is walked past now, and named here instead. Held per path and replaced on every
reading of the folder it lies in, so a permission put right disappears by itself.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unreadable_files",
        sa.Column("relative_path", sa.String(length=1024), primary_key=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "last_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("unreadable_files")
