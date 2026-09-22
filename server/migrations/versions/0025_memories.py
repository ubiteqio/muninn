"""Memories

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-21

"Heute vor X Jahren": for a day, one memory per earlier year that has photos from that
calendar day, with up to twelve of them. Chosen once per day - at 06:00, or when somebody asks
first - so the cards stay the same all day long.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        #: The day it is shown on.
        sa.Column("day", sa.Date(), nullable=False),
        #: The year the photos are from.
        sa.Column("year", sa.Integer(), nullable=False),
        #: True when the day itself had nothing and the week around it was taken.
        sa.Column("from_week", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "album_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("day", "year", name="uq_memories_day_year"),
    )
    op.create_table(
        "memory_media",
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("memory_media")
    op.drop_table("memories")
