"""A book of several folders

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-27

Some folders belong together - a holiday split into days, a child's year kept month by month -
and a book of one of them is a book of a fragment. A book now draws from as many folders as an
admin chooses.

The album on the book itself stays: it is where the book hangs in the tree and where its title
comes from. The folders it draws from are listed here, the home album among them, so the books
already on the shelf need no thought - each gets its one folder.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE photobook_albums (
            photobook_id uuid NOT NULL REFERENCES photobooks(id) ON DELETE CASCADE,
            album_id uuid NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
            PRIMARY KEY (photobook_id, album_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_photobook_albums_album_id ON photobook_albums (album_id)")
    # What is on the shelf already draws from the one folder it was made of.
    op.execute(
        "INSERT INTO photobook_albums (photobook_id, album_id) SELECT id, album_id FROM photobooks"
    )


def downgrade() -> None:
    op.execute("DROP TABLE photobook_albums")
