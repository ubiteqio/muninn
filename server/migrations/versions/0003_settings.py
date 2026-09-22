"""Settings an admin may change at runtime

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20

Derivative sizes and the scanner's ignore list were fixed in the concept. They become settings of
the installation, so the admin area can change them without a redeploy. The table holds a single
row, created here with the values the concept named.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED = sa.text(
    """
    INSERT INTO settings (id, thumbnail_size, preview_size, image_quality, video_height,
                          ignored_names)
    VALUES (1, 400, 2048, 82, 720, ARRAY['@eaDir', '#recycle', '.DS_Store', 'Thumbs.db'])
    """
)


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("thumbnail_size", sa.Integer(), nullable=False),
        sa.Column("preview_size", sa.Integer(), nullable=False),
        sa.Column("image_quality", sa.Integer(), nullable=False),
        sa.Column("video_height", sa.Integer(), nullable=False),
        sa.Column("ignored_names", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_settings_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
    )
    op.execute(SEED)


def downgrade() -> None:
    op.drop_table("settings")
