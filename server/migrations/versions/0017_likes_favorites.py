"""Likes and favourites

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-21

A like and a favourite each point at a medium or an album - exactly one of them. The foreign
keys take them along when the medium or album goes for good. Likes on comments follow with the
comments.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("likes", "favorites")


def upgrade() -> None:
    for table in TABLES:
        op.create_table(
            table,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "media_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("media.id", ondelete="CASCADE"),
            ),
            sa.Column(
                "album_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("albums.id", ondelete="CASCADE"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "num_nonnulls(media_id, album_id) = 1", name=f"ck_{table}_one_target"
            ),
        )
        # One per person and thing; the partial indexes also serve counting per thing.
        op.create_index(
            f"uq_{table}_user_media",
            table,
            ["media_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("media_id IS NOT NULL"),
        )
        op.create_index(
            f"uq_{table}_user_album",
            table,
            ["album_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("album_id IS NOT NULL"),
        )
        op.create_index(f"ix_{table}_user_created", table, ["user_id", "created_at"])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
