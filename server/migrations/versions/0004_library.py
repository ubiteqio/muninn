"""The library: roots, albums, media and their files

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20

Folders on the NAS become albums, files become media. A medium is identified by its id and the
BLAKE3 hash of its primary file, never by a path, so renaming or moving a file on the NAS keeps
everything that hangs on the medium.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCAN_STATUS = sa.Enum(
    "never", "running", "ok", "paused", "unavailable", "failed", name="scan_status"
)
MEDIA_KIND = sa.Enum("image", "video", name="media_kind")
MEDIA_STATUS = sa.Enum("active", "missing", name="media_status")
MEDIA_FILE_ROLE = sa.Enum("primary", "raw", "motion", name="media_file_role")
DATE_SOURCE = sa.Enum("exif", "gps", "filename", "folder_name", "file_mtime", name="date_source")

TIMESTAMPS = (
    sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    ),
)


def upgrade() -> None:
    op.create_table(
        "library_roots",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_status", SCAN_STATUS, nullable=False),
        sa.Column("last_scan_message", sa.Text(), nullable=True),
        sa.Column("pending_deletions", sa.Integer(), nullable=False),
        *TIMESTAMPS,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_roots")),
        sa.UniqueConstraint("path", name=op.f("uq_library_roots_path")),
    )

    op.create_table(
        "albums",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("root_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("folder_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *TIMESTAMPS,
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name=op.f("fk_albums_root_id_library_roots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["albums.id"],
            name=op.f("fk_albums_parent_id_albums"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_albums")),
        sa.UniqueConstraint("root_id", "relative_path", name="uq_albums_root_id_relative_path"),
    )
    op.create_index("ix_albums_parent_id", "albums", ["parent_id"])

    op.create_table(
        "media",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("root_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("album_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", MEDIA_KIND, nullable=False),
        sa.Column("status", MEDIA_STATUS, nullable=False),
        sa.Column("missing_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("taken_at_source", DATE_SOURCE, nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("camera_make", sa.String(length=120), nullable=True),
        sa.Column("camera_model", sa.String(length=120), nullable=True),
        sa.Column("lens", sa.String(length=160), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("metadata_version", sa.SmallInteger(), nullable=False),
        *TIMESTAMPS,
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name=op.f("fk_media_root_id_library_roots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["album_id"], ["albums.id"], name=op.f("fk_media_album_id_albums"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
    )
    op.create_index("ix_media_album_id_taken_at", "media", ["album_id", "taken_at"])
    op.create_index("ix_media_content_hash", "media", ["content_hash"])
    op.create_index("ix_media_root_id_status", "media", ["root_id", "status"])

    op.create_table(
        "media_files",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("root_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("role", MEDIA_FILE_ROLE, nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        *TIMESTAMPS,
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_media_files_media_id_media"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name=op.f("fk_media_files_root_id_library_roots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_files")),
        sa.UniqueConstraint(
            "root_id", "relative_path", name="uq_media_files_root_id_relative_path"
        ),
    )
    op.create_index("ix_media_files_content_hash", "media_files", ["content_hash"])


def downgrade() -> None:
    op.drop_table("media_files")
    op.drop_table("media")
    op.drop_table("albums")
    op.drop_table("library_roots")

    for enum in (MEDIA_FILE_ROLE, DATE_SOURCE, MEDIA_STATUS, MEDIA_KIND, SCAN_STATUS):
        enum.drop(op.get_bind(), checkfirst=False)
