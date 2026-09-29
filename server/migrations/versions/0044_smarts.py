"""Smarts: chapters an album falls into

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-26

A folder of thousands of pictures is browsed by what is in the pictures, not by scrolling. The
groups are found once by a worker - from the vectors that are already in this database, so no
machine has to answer for it - and written down here. Everything can be thrown away and built
again; nothing anybody typed lives in these tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "smart_chapters",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "album_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="look"),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tags",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "cover_media_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("from_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("until_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tightness", sa.Float(), nullable=False, server_default="0"),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column(
            "built_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_smart_chapters_album_id", "smart_chapters", ["album_id"])
    op.create_index("ix_smart_chapters_size", "smart_chapters", ["size"])

    op.create_table(
        "smart_chapter_media",
        sa.Column(
            "chapter_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("smart_chapters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "media_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_smart_chapter_media_media_id", "smart_chapter_media", ["media_id"])


def downgrade() -> None:
    op.drop_index("ix_smart_chapter_media_media_id", table_name="smart_chapter_media")
    op.drop_table("smart_chapter_media")
    op.drop_index("ix_smart_chapters_size", table_name="smart_chapters")
    op.drop_index("ix_smart_chapters_album_id", table_name="smart_chapters")
    op.drop_table("smart_chapters")
