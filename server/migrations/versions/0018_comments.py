"""Comments, their mentions, and likes on comments

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-21

A comment belongs to a medium or an album and may answer one other comment - one level, no
deeper. Who it mentions is kept beside it, for the notifications. A comment that was answered
and then deleted keeps its place with an empty text, so the answers still make sense. Likes
learn to point at comments.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id", ondelete="CASCADE")
        ),
        sa.Column(
            "album_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="CASCADE"),
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("num_nonnulls(media_id, album_id) = 1", name="ck_comments_one_target"),
    )
    op.create_index("ix_comments_media", "comments", ["media_id", "created_at"])
    op.create_index("ix_comments_album", "comments", ["album_id", "created_at"])
    op.create_index("ix_comments_parent", "comments", ["parent_id"])

    op.create_table(
        "comment_mentions",
        sa.Column(
            "comment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.add_column(
        "likes",
        sa.Column(
            "comment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="CASCADE"),
        ),
    )
    op.drop_constraint("ck_likes_one_target", "likes", type_="check")
    op.create_check_constraint(
        "ck_likes_one_target", "likes", "num_nonnulls(media_id, album_id, comment_id) = 1"
    )
    op.create_index(
        "uq_likes_user_comment",
        "likes",
        ["comment_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("comment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_likes_user_comment", table_name="likes")
    op.execute("DELETE FROM likes WHERE comment_id IS NOT NULL")
    op.drop_constraint("ck_likes_one_target", "likes", type_="check")
    op.create_check_constraint(
        "ck_likes_one_target", "likes", "num_nonnulls(media_id, album_id) = 1"
    )
    op.drop_column("likes", "comment_id")
    op.drop_table("comment_mentions")
    op.drop_table("comments")
