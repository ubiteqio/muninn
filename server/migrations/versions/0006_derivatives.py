"""Stage 3: where the previews of a medium lie

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20

Originals stay on the NAS and are never touched. What people browse through are the derivatives
on the local SSD; these columns say where they are and which version of the stage made them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ["thumbnail_path", "preview_path", "video_path", "poster_path"]


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column("derive_version", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    for name in COLUMNS:
        op.add_column("media", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column("media", name)
    op.drop_column("media", "derive_version")
