"""Derived bytes

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-22

How much room a medium's thumbnail, preview, playable video and poster take on the server, so the
overview can set it beside the originals. Written by stage 3 whenever it makes them; media derived
before this revision are measured once by hand.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media", sa.Column("derived_bytes", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("media", "derived_bytes")
