"""Faces and persons

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-21

Every face found in a medium, with its box and its ArcFace vector, and the persons they belong
to. A face gets its person from a user naming its group, or automatically when it lies very
close to faces already named; a face that lies only fairly close carries a suggestion instead.
A suggestion somebody said no to is remembered, so it is not asked again.

A person is only ever made by somebody naming it. Faces without a person are grouped by a job
(cluster), so the app can offer "who is this?" for a whole group at once.

The vector lives in the faces table like the other vectors do: halfvec, with its model and
length, an HNSW index per model created when its first vector arrives (muninn.search).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_kind ADD VALUE IF NOT EXISTS 'face_detector'")

    op.create_table(
        "persons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        #: Strangers in the background: kept, so their faces are not asked about again.
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute("CREATE UNIQUE INDEX uq_persons_name ON persons (lower(name))")

    op.execute(
        """
        CREATE TABLE faces (
            id uuid PRIMARY KEY,
            media_id uuid NOT NULL REFERENCES media (id) ON DELETE CASCADE,
            -- Where it is, as fractions of the picture's width and height.
            box_left real NOT NULL,
            box_top real NOT NULL,
            box_right real NOT NULL,
            box_bottom real NOT NULL,
            score real NOT NULL,
            -- Its smaller side in pixels of the picture that was looked at.
            pixels integer NOT NULL,
            -- For a video, the second it was seen at.
            second real,
            model text NOT NULL,
            dimensions smallint NOT NULL,
            embedding halfvec NOT NULL,
            person_id uuid REFERENCES persons (id) ON DELETE SET NULL,
            -- "user" when somebody said who it is, "auto" when it was that close.
            assigned_by varchar(8),
            suggested_person_id uuid REFERENCES persons (id) ON DELETE SET NULL,
            -- The group the job put it in while it has no person.
            cluster integer,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (vector_dims(embedding) = dimensions)
        )
        """
    )
    op.create_index("ix_faces_media_id", "faces", ["media_id"])
    op.create_index("ix_faces_person_id", "faces", ["person_id"])
    op.create_index("ix_faces_cluster", "faces", ["cluster"])
    op.create_index("ix_faces_suggested_person_id", "faces", ["suggested_person_id"])

    op.create_table(
        "face_rejections",
        sa.Column(
            "face_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("faces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.add_column(
        "media",
        sa.Column("face_version", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("media", "face_version")
    op.drop_table("face_rejections")
    op.execute("DROP TABLE faces")
    op.drop_table("persons")
