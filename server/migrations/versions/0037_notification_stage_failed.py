"""What went wrong, on the bell

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-24

A stage that gives up on a medium says so in the engine room and nowhere else: an admin has to
already suspect something to go and look. It tells them now, on the bell, and carries the
machine's own words with it - ffmpeg's complaint, the detector's refusal - so the reason is
read where the entry is, not looked up afterwards.

Two columns for that: which stage gave up, and what it said.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("stage", sa.String(length=24), nullable=True))
    op.add_column("notifications", sa.Column("detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "detail")
    op.drop_column("notifications", "stage")
