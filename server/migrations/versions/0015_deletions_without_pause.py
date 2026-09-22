"""Deletions on the NAS reach the albums without a confirmation

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-21

The pause before many deletions at once is off from now on: 0 in both thresholds. A folder that
is waiting for a confirmation is let go, and its next read marks the files as missing.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE settings SET deletion_share_percent = 0, deletion_count = 0")
    op.execute("UPDATE publications SET pending_deletions = 0 WHERE pending_deletions > 0")


def downgrade() -> None:
    op.execute("UPDATE settings SET deletion_share_percent = 5, deletion_count = 500")
