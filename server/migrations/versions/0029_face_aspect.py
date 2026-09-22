"""Face aspect

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-21

The width of the picture a face was found in, divided by its height. The box is kept as
fractions of both; to cut a square around the face the app needs to know how they compare.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("faces", sa.Column("aspect", sa.Float(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("faces", "aspect")
