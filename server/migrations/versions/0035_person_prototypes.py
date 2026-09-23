"""Person prototypes

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-23

A face was recognised by whichever single face of a person happened to lie nearest, which made
it a matter of luck which photo that was. In an archive of twenty-six years a person at two and
the same person at thirty lie far apart, and no single face speaks for both.

A person is kept as a handful of middles instead: their confirmed faces gathered into a few
groups, one for each way they looked. Filled by the pass that looks at the faces again, so
nothing has to be computed here.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE person_prototypes (
            id uuid PRIMARY KEY,
            person_id uuid NOT NULL REFERENCES persons (id) ON DELETE CASCADE,
            model text NOT NULL,
            dimensions smallint NOT NULL,
            center halfvec NOT NULL,
            -- How many faces this middle was made of, so a thin one can be told from a full one.
            faces integer NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (vector_dims(center) = dimensions)
        )
        """
    )
    op.create_index("ix_person_prototypes_person_id", "person_prototypes", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_person_prototypes_person_id", table_name="person_prototypes")
    op.execute("DROP TABLE person_prototypes")
