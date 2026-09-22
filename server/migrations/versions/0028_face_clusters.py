"""Face clusters

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-21

Numbers for the groups of unnamed faces, handed out as groups form.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE face_clusters")


def downgrade() -> None:
    op.execute("DROP SEQUENCE face_clusters")
