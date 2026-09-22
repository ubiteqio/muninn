"""Everything known about a medium can be searched for

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-21

What the file itself says - camera, model, lens - becomes a word index of its own, kept up to
date by PostgreSQL. The describing model's scene and time of day join its caption, tags and text
in the picture. Album paths and file names get trigram indexes, so a search that forgives typing
errors stays fast on a large library. The vector indexes are rebuilt to filter by model and
vector length.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The same full text the analysis service writes, for the answers stored before.
REWRITE_ANALYSES = """
    UPDATE media_analyses SET search_tsv =
        setweight(to_tsvector('german', caption), 'A')
        || setweight(to_tsvector('german', array_to_string(tags, ' ') || ' ' || scene), 'B')
        || setweight(to_tsvector('german', ocr_text || ' ' || time_of_day), 'C')
"""


#: The vector indexes of the first vectors filtered by model only. They are rebuilt, filtering
#: by model and length, when the next vector of their model arrives.
DROP_OLD_VECTOR_INDEXES = """
    DO $$
    DECLARE found record;
    BEGIN
        FOR found IN
            SELECT indexname FROM pg_indexes
             WHERE tablename IN ('image_embeddings', 'caption_embeddings')
               AND indexdef LIKE '%USING hnsw%'
        LOOP
            EXECUTE format('DROP INDEX %I', found.indexname);
        END LOOP;
    END $$
"""


def upgrade() -> None:
    op.execute(DROP_OLD_VECTOR_INDEXES)
    op.execute(
        """
        ALTER TABLE media ADD COLUMN metadata_tsv tsvector GENERATED ALWAYS AS (
            to_tsvector(
                'simple'::regconfig,
                coalesce(camera_make, '') || ' ' || coalesce(camera_model, '') || ' '
                || coalesce(lens, '')
            )
        ) STORED
        """
    )
    op.execute("CREATE INDEX ix_media_metadata_tsv ON media USING gin (metadata_tsv)")
    op.execute(
        "CREATE INDEX ix_albums_relative_path_trgm ON albums USING gin (relative_path gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_media_files_filename_trgm ON media_files USING gin (filename gin_trgm_ops)"
    )
    op.execute(REWRITE_ANALYSES)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_media_files_filename_trgm")
    op.execute("DROP INDEX IF EXISTS ix_albums_relative_path_trgm")
    op.execute("DROP INDEX IF EXISTS ix_media_metadata_tsv")
    op.execute("ALTER TABLE media DROP COLUMN IF EXISTS metadata_tsv")
