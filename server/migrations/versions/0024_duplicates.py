"""Duplicates

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-21

Every medium gets a fingerprint of its picture (muninn.duplicates.fingerprint), and a job puts
media that are the same file, nearly the same picture, or shots of a burst into groups. An admin
may hide all but one of a group: duplicate_of then points at the one that stays. Nothing is
deleted - the NAS is read-only - but hidden media leave albums, timeline, search and map.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media", sa.Column("fingerprint", sa.BigInteger()))
    op.add_column(
        "media",
        sa.Column("fingerprint_version", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "media",
        sa.Column(
            "duplicate_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
        ),
    )
    op.create_index(
        "ix_media_duplicate_of",
        "media",
        ["duplicate_of"],
        postgresql_where=sa.text("duplicate_of IS NOT NULL"),
    )
    # Bursts are found by looking a few seconds ahead of every photo.
    op.create_index("ix_media_taken_at", "media", ["taken_at"])
    op.create_table(
        "duplicate_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        #: exact, near or burst: the loosest tie inside the group.
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("newest", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "duplicate_members",
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("duplicate_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "media_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        #: The one to keep: largest, most complete metadata, original format.
        sa.Column("best", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_duplicate_members_media_id", "duplicate_members", ["media_id"])


def downgrade() -> None:
    op.drop_table("duplicate_members")
    op.drop_table("duplicate_groups")
    op.drop_index("ix_media_taken_at", table_name="media")
    op.drop_index("ix_media_duplicate_of", table_name="media")
    op.drop_column("media", "duplicate_of")
    op.drop_column("media", "fingerprint_version")
    op.drop_column("media", "fingerprint")
