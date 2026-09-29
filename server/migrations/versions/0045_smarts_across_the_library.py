"""Smarts across the whole library

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-26

A chapter belonged to one folder, which made it a second way of browsing the same folder. It
now belongs to the library: four days in one town, a day with two hundred pictures, everybody
named in one year, the feasts of twenty years, and the motifs that run through all of it - each
found by its own rule, each spanning whatever folders its media happen to lie in.

What a chapter is called is kept as a key and its values, not as a sentence: the German belongs
in the app's texts, not in this database.

Everything here is derived, so the old chapters are simply dropped; the next run writes new ones.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Derived, and of the old shape: they go, and are found again on the next run.
    op.execute("DELETE FROM smart_chapters")

    op.alter_column("smart_chapters", "album_id", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        "smart_chapters", sa.Column("albums", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "smart_chapters",
        sa.Column("title_key", sa.String(length=32), nullable=False, server_default="motif"),
    )
    op.add_column(
        "smart_chapters",
        sa.Column(
            "title_args",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "smart_chapters", sa.Column("rank", sa.Integer(), nullable=False, server_default="0")
    )
    op.drop_column("smart_chapters", "title")
    op.create_index("ix_smart_chapters_kind", "smart_chapters", ["kind"])
    op.create_index("ix_smart_chapters_rank", "smart_chapters", ["rank"])

    op.add_column(
        "settings",
        sa.Column("smart_max_media", sa.Integer(), nullable=False, server_default="500"),
    )


def downgrade() -> None:
    op.drop_column("settings", "smart_max_media")
    op.drop_index("ix_smart_chapters_rank", table_name="smart_chapters")
    op.drop_index("ix_smart_chapters_kind", table_name="smart_chapters")
    op.drop_column("smart_chapters", "rank")
    op.add_column(
        "smart_chapters", sa.Column("title", sa.Text(), nullable=False, server_default="")
    )
    op.drop_column("smart_chapters", "title_args")
    op.drop_column("smart_chapters", "title_key")
    op.drop_column("smart_chapters", "albums")
    op.execute("DELETE FROM smart_chapters")
    op.alter_column("smart_chapters", "album_id", existing_type=sa.UUID(), nullable=False)
