"""Excluded folders

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-21

A published folder takes everything below it. An admin may switch single subfolders off again:
they are left out when the folder is read, and their albums and media leave Muninn. The NAS is
not touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column(
            "excluded_paths",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("publications", "excluded_paths")
