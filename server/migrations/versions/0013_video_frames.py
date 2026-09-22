"""What the describing model saw in each second of a video

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-21

Stage 5 looks at a video one frame per second and skips the seconds in which nothing changed.
Every frame it did look at keeps its answer here, with the second it belongs to, so a search can
later lead to the moment and not only to the video.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_frames",
        sa.Column(
            "media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("second", sa.Integer(), primary_key=True),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("ocr_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("people_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=False),
    )
    op.create_index(
        "ix_video_frames_search_tsv", "video_frames", ["search_tsv"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_table("video_frames")
