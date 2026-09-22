"""What is said in a video

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-21

A third kind of AI profile, the transcriber, and one transcript per video: the text, when each
part of it was said, the language, and which model heard it. The full text is written together
with the transcript, in German stems when the video speaks German and word for word otherwise.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_kind ADD VALUE IF NOT EXISTS 'transcriber'")

    op.create_table(
        "media_transcripts",
        sa.Column(
            "media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "segments", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=False),
        sa.Column(
            "transcribed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_media_transcripts_model", "media_transcripts", ["model"])
    op.create_index(
        "ix_media_transcripts_search_tsv",
        "media_transcripts",
        ["search_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("media_transcripts")
    # PostgreSQL cannot take a value out of an enum; the profiles that use it go instead.
    op.execute("DELETE FROM ai_profiles WHERE kind = 'transcriber'")
