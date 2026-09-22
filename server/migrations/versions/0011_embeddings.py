"""Vectors of pictures and of their descriptions

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-21

One table per kind, and the model as a column. The concept wants a new model to fill its vectors
beside the old ones and take over only when it is complete; a table per model would do that too,
but would appear at runtime whenever somebody typed a model name into the admin area - and schema
changes happen here, in migrations, and nowhere else.

The column has no fixed length, because models differ in it. What makes a search fast is a
partial HNSW index per model, cast to that model's length; the search module creates it the first
time a model's vectors are written, because only then is the length known.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("image_embeddings", "caption_embeddings")


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"""
            CREATE TABLE {table} (
                media_id uuid NOT NULL REFERENCES media (id) ON DELETE CASCADE,
                model text NOT NULL,
                -- How the stage made it: a new input size or a new crop means new vectors.
                version smallint NOT NULL,
                dimensions smallint NOT NULL,
                embedding halfvec NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (media_id, model),
                CHECK (vector_dims(embedding) = dimensions)
            )
            """
        )
        # "Which media have no vector for this model yet" is asked every minute.
        op.execute(f"CREATE INDEX ix_{table}_model ON {table} (model)")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
