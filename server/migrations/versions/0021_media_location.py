"""Media location

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-21

The map needs the coordinates as a PostGIS point: clustering per zoom level and asking which
media lie in the visible part of the map both want a spatial index. The point is generated from
the plain degrees the metadata stage writes, so nothing else has to keep the two in step.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE media ADD COLUMN location geometry(Point, 4326)
        GENERATED ALWAYS AS (
            CASE WHEN latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
                THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            END
        ) STORED
        """
    )
    op.execute("CREATE INDEX ix_media_location ON media USING gist (location)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_media_location")
    op.execute("ALTER TABLE media DROP COLUMN location")
