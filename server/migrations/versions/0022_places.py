"""Places

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-21

The places of the world from GeoNames, and for each medium with coordinates the one it was
taken at or near. "keys" holds every name a place may be searched by, its region's and its
country's included, so "Toskana" finds the photos from Florence.

A medium remembers the point it was placed for: when its coordinates change, the two differ and
it is placed again. place_version is the version of the gazetteer that placed it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("region", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "keys",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.execute(
        """
        ALTER TABLE places ADD COLUMN location geometry(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)) STORED
        """
    )
    op.execute("CREATE INDEX ix_places_location ON places USING gist (location)")
    op.execute("CREATE INDEX ix_places_keys ON places USING gin (keys)")

    op.add_column(
        "media",
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id", ondelete="SET NULL")),
    )
    op.add_column(
        "media",
        sa.Column("place_version", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.execute("ALTER TABLE media ADD COLUMN placed_for geometry(Point, 4326)")
    op.create_index("ix_media_place_id", "media", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_media_place_id", table_name="media")
    op.drop_column("media", "placed_for")
    op.drop_column("media", "place_version")
    op.drop_column("media", "place_id")
    op.drop_table("places")
