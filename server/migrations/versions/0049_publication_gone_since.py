"""When a published folder was first found deleted on the NAS

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-29

A published folder that is gone was only ever reported as unreachable, and nothing of it was
cleaned up - not its albums, not the files that waited in it. Once it is proven gone on two reads
a stability window apart, it is now taken out of the albums by itself. This is when the first of
the two saw it gone.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE publications ADD COLUMN gone_since timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE publications DROP COLUMN gone_since")
