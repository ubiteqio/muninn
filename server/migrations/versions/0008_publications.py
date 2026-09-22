"""One library, and the folders published from it

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-20

The folder the host mounts is the library; it is not chosen in Muninn. What is chosen is which
folders below it appear under Albums - with everything beneath them, and in the place the original
has, so an album is found where one expects it. Paths are therefore relative to the library, and
the several "roots" of before become one list of published folders.

The indexed data cannot be carried over: paths used to be relative to a root, and there is no
root any more. Everything read from the NAS is therefore thrown away and read again; nothing is
lost that the originals do not still hold.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The type exists since 0004; referring to it must not try to create it again.
SCAN_STATUS = postgresql.ENUM(name="scan_status", create_type=False)


def upgrade() -> None:
    # What was indexed is derived data; the originals on the NAS are the truth and are re-read.
    op.execute(sa.text("TRUNCATE albums, media, media_files, pending_files, change_log CASCADE"))

    op.create_table(
        "publications",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", SCAN_STATUS, nullable=False),
        sa.Column("last_sync_message", sa.Text(), nullable=True),
        sa.Column("pending_deletions", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publications")),
        sa.UniqueConstraint("relative_path", name=op.f("uq_publications_relative_path")),
    )

    # Albums: one library, so the path alone identifies a folder. An album that is only the way
    # to a published one further down carries no media and is not read.
    op.drop_constraint("uq_albums_root_id_relative_path", "albums", type_="unique")
    op.drop_constraint(op.f("fk_albums_root_id_library_roots"), "albums", type_="foreignkey")
    op.drop_column("albums", "root_id")
    op.create_unique_constraint(op.f("uq_albums_relative_path"), "albums", ["relative_path"])
    op.add_column(
        "albums", sa.Column("is_source", sa.Boolean(), nullable=False, server_default=sa.false())
    )

    op.drop_index("ix_media_root_id_status", table_name="media")
    op.drop_constraint(op.f("fk_media_root_id_library_roots"), "media", type_="foreignkey")
    op.drop_column("media", "root_id")
    op.create_index("ix_media_status", "media", ["status"])

    op.drop_constraint("uq_media_files_root_id_relative_path", "media_files", type_="unique")
    op.drop_constraint(
        op.f("fk_media_files_root_id_library_roots"), "media_files", type_="foreignkey"
    )
    op.drop_column("media_files", "root_id")
    op.create_unique_constraint(
        op.f("uq_media_files_relative_path"), "media_files", ["relative_path"]
    )

    op.drop_constraint("uq_pending_files_root_id_relative_path", "pending_files", type_="unique")
    op.drop_constraint(
        op.f("fk_pending_files_root_id_library_roots"), "pending_files", type_="foreignkey"
    )
    op.drop_column("pending_files", "root_id")
    op.create_unique_constraint(
        op.f("uq_pending_files_relative_path"), "pending_files", ["relative_path"]
    )

    op.drop_constraint(
        op.f("fk_change_log_root_id_library_roots"), "change_log", type_="foreignkey"
    )
    op.drop_column("change_log", "root_id")

    op.drop_table("library_roots")


def downgrade() -> None:
    op.execute(sa.text("TRUNCATE albums, media, media_files, pending_files, change_log CASCADE"))

    op.create_table(
        "library_roots",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_status", SCAN_STATUS, nullable=False),
        sa.Column("last_scan_message", sa.Text(), nullable=True),
        sa.Column("pending_deletions", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_roots")),
        sa.UniqueConstraint("path", name=op.f("uq_library_roots_path")),
    )

    for table in ("albums", "media", "media_files", "pending_files", "change_log"):
        op.add_column(table, sa.Column("root_id", sa.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_root_id_library_roots"),
            table,
            "library_roots",
            ["root_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.drop_column("albums", "is_source")
    op.drop_constraint(op.f("uq_albums_relative_path"), "albums", type_="unique")
    op.drop_index("ix_media_status", table_name="media")
    op.drop_constraint(op.f("uq_media_files_relative_path"), "media_files", type_="unique")
    op.drop_constraint(op.f("uq_pending_files_relative_path"), "pending_files", type_="unique")
    op.drop_table("publications")
