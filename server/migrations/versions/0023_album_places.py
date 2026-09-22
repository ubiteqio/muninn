"""Album places

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-21

Many older photos have no coordinates. An album can be given a place, which its media without
coordinates inherit - and those in the albums below it, unless one of them has a place of its
own. Such a medium carries place_estimated, so the app says "geschätzt".

The names of places get an index for looking them up while typing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "albums",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id", ondelete="SET NULL")),
    )
    op.add_column(
        "media",
        sa.Column("place_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("CREATE INDEX ix_places_name_prefix ON places (lower(name) text_pattern_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_places_name_prefix")
    op.drop_column("media", "place_estimated")
    op.drop_column("albums", "place_id")
