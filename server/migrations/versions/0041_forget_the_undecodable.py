"""Forget the failures a strict decode caused

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-24

exiftool and ffprobe print whatever was written into a file years ago. Their output was read
as strict UTF-8, so a 3GP from 2010 with one byte that is not UTF-8 raised before a single
field could be read - and the stage died for that medium rather than for that byte. Three
times, and the clock gave those media up for good.

The output is read leniently now. The attempts that strictness wrote down were never the
media's fault, so they go and the clock picks those media up again by itself.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNDECODABLE = """
    DELETE FROM media_attempts
     WHERE last_error LIKE '%%UnicodeDecodeError%%'
"""

_NOTIFIED = """
    DELETE FROM notifications
     WHERE kind = 'stage_failed' AND detail LIKE '%%UnicodeDecodeError%%'
"""


def upgrade() -> None:
    for statement in (_UNDECODABLE, _NOTIFIED):
        op.execute(statement)


def downgrade() -> None:
    """What was forgotten cannot be remembered, and should not be."""
