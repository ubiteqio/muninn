"""Fotobücher

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-27

A book of an album: its pages built once and kept, because building them costs the machine that
describes the pictures, and because a book that rearranged itself whenever the folder grew would
be no book at all. Several books may come from one album; the seed is what makes the second one
different from the first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photobooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "album_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=False, server_default=""),
        sa.Column("style", sa.String(length=16), nullable=False, server_default="scrapbook"),
        sa.Column("size", sa.String(length=8), nullable=False, server_default="medium"),
        sa.Column("max_media", sa.Integer(), nullable=False, server_default="150"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="building"),
        sa.Column("trouble", sa.Text(), nullable=False, server_default=""),
        sa.Column("written", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "pages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("media_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "cover_media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
        ),
        sa.Column("from_at", sa.DateTime(timezone=True)),
        sa.Column("until_at", sa.DateTime(timezone=True)),
        sa.Column("built_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_photobooks_album_id", "photobooks", ["album_id"])
    op.create_index("ix_photobooks_created_at", "photobooks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_photobooks_created_at", table_name="photobooks")
    op.drop_index("ix_photobooks_album_id", table_name="photobooks")
    op.drop_table("photobooks")
