"""Remember which file system a library root sits on

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-20

A share that is not mounted looks exactly like an empty folder. Muninn therefore remembers the
device the folder was on when it was set up and refuses to sync when that changed - which makes
the marker file optional, and picking a folder in the admin area a great deal simpler.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("library_roots", sa.Column("device_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("library_roots", "device_id")
