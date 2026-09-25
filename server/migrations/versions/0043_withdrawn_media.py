"""Media an admin has taken down

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-25

A picture nobody should see has to go now, not at the next pass. Taking it down deletes it and
everything that hung on it - the previews, the vectors, the faces, the description, what was
said about it and who liked it.

The file itself stays on the NAS, because originals are never written to. So the next reading
would find it, index it again and show it again within the minute. What is remembered here is
that it was taken down: by its content hash, which is what identifies a medium, so it stays
down after a rename or a move.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "withdrawn_media",
        sa.Column("content_hash", sa.String(length=64), primary_key=True),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column(
            "withdrawn_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "withdrawn_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_withdrawn_media_relative_path", "withdrawn_media", ["relative_path"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawn_media_relative_path", table_name="withdrawn_media")
    op.drop_table("withdrawn_media")
