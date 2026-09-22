"""What the describing model saw in a medium

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21

One row per medium: the caption, tags and the rest of stage 5's answer, which model gave it and
under which stage version. The German full-text column is written together with the answer; it
cannot be a generated column because joining the tags is not immutable in PostgreSQL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_analyses",
        sa.Column(
            "media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("scene", sa.Text(), nullable=False, server_default=""),
        sa.Column("ocr_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("people_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("time_of_day", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_screenshot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_document", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("quality", sa.Text(), nullable=False, server_default=""),
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=False),
        sa.Column(
            "analyzed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_media_analyses_model", "media_analyses", ["model"])
    op.create_index(
        "ix_media_analyses_search_tsv", "media_analyses", ["search_tsv"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_table("media_analyses")
