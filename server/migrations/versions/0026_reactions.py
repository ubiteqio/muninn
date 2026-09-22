"""Reactions

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-21

A like on a medium is one of a few reactions now - a heart, a thumb, a laugh and so on - one
per person. Every like so far was a heart. Albums and comments keep the plain heart.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REACTIONS = ("heart", "thumbs_up", "joy", "wow", "moved", "clap", "fire", "hang_loose")


def upgrade() -> None:
    op.add_column(
        "likes",
        sa.Column("reaction", sa.String(16), nullable=False, server_default="heart"),
    )
    allowed = ", ".join(f"'{reaction}'" for reaction in REACTIONS)
    op.create_check_constraint("ck_likes_reaction", "likes", f"reaction IN ({allowed})")


def downgrade() -> None:
    op.drop_constraint("ck_likes_reaction", "likes", type_="check")
    op.drop_column("likes", "reaction")
