"""Faces switch

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-21

Faces are biometric data: the admin may switch looking for them off. On by default, as the
concept has the feature in version 1.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("faces_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("settings", "faces_enabled")
