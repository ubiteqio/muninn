"""Forget the failures our own request size caused

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-24

Face detection sent a whole video's frames in one request. The machine names how many it takes
at once and refused the rest with a 413, so a long video came back without faces however good
it was - three times, and then the clock gave up on it for good.

The request is split now. The attempts that refusal wrote down were never the media's fault,
so they go, and the clock picks those media up again by itself.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM media_attempts
         WHERE stage = 'faces' AND last_error LIKE '%%At most%%inputs at a time%%'
        """
    )
    # The bell told the admins about media that were never at fault; those entries go with them.
    op.execute(
        """
        DELETE FROM notifications
         WHERE kind = 'stage_failed' AND stage = 'faces'
           AND detail LIKE '%%At most%%inputs at a time%%'
        """
    )


def downgrade() -> None:
    """What was forgotten cannot be remembered, and should not be."""
