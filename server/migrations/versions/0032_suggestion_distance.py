"""Suggestion distance

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-22

How close a suggested face lay to the person it is suggested for, so the app can say how alike
they are. Filled whenever a suggestion is made; the next look at the faces fills the old ones.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("faces", sa.Column("suggested_distance", sa.Float()))


def downgrade() -> None:
    op.drop_column("faces", "suggested_distance")
