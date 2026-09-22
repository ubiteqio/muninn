"""Reconciliation with the NAS: signatures, quick hashes, waiting files and the change log

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20

The concept spells out how Muninn notices what happened on a share it gets no events from: a
signature per folder, a comparison in three stages, two observations before a file counts as
copied, and a log of everything that was derived from it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The type exists since 0004; referring to it must not try to create it again.
SCAN_STATUS = postgresql.ENUM(name="scan_status", create_type=False)
CHANGE_KIND = sa.Enum(
    "album_added",
    "album_removed",
    "media_added",
    "media_changed",
    "media_touched",
    "media_moved",
    "media_missing",
    "media_restored",
    "media_removed",
    name="change_kind",
)
SYNC_TRIGGER = sa.Enum("quick", "full", "manual", "agent", name="sync_trigger")

#: The defaults of the concept's settings table, written into the single settings row.
SETTINGS_COLUMNS = [
    ("quick_sync_seconds", sa.Integer(), "300"),
    ("full_sync_hour", sa.SmallInteger(), "3"),
    ("stability_seconds", sa.Integer(), "30"),
    ("missing_grace_days", sa.Integer(), "30"),
    ("deletion_share_percent", sa.SmallInteger(), "5"),
    ("deletion_count", sa.Integer(), "500"),
]


def upgrade() -> None:
    # Albums: the signature of the last complete listing replaces the folder's modification time.
    op.add_column("albums", sa.Column("entry_signature", sa.String(length=64), nullable=True))
    op.add_column("albums", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "albums",
        sa.Column("last_sync_status", SCAN_STATUS, nullable=False, server_default="never"),
    )
    op.add_column("albums", sa.Column("last_sync_message", sa.Text(), nullable=True))
    op.drop_column("albums", "folder_modified_at")

    op.add_column("media", sa.Column("quick_hash", sa.String(length=64), nullable=True))
    op.add_column("media", sa.Column("pixel_hash", sa.String(length=64), nullable=True))
    op.add_column("media_files", sa.Column("quick_hash", sa.String(length=64), nullable=True))

    for name, column_type, default in SETTINGS_COLUMNS:
        op.add_column(
            "settings", sa.Column(name, column_type, nullable=False, server_default=default)
        )
    op.add_column(
        "settings",
        sa.Column("nas_agent_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "pending_files",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("root_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name=op.f("fk_pending_files_root_id_library_roots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pending_files")),
        sa.UniqueConstraint(
            "root_id", "relative_path", name="uq_pending_files_root_id_relative_path"
        ),
    )

    op.create_table(
        "change_log",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("root_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("album_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("media_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", CHANGE_KIND, nullable=False),
        sa.Column("trigger", SYNC_TRIGGER, nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["root_id"],
            ["library_roots.id"],
            name=op.f("fk_change_log_root_id_library_roots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["album_id"],
            ["albums.id"],
            name=op.f("fk_change_log_album_id_albums"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_change_log_media_id_media"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_log")),
    )
    op.create_index("ix_change_log_occurred_at", "change_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("change_log")
    op.drop_table("pending_files")

    op.drop_column("settings", "nas_agent_enabled")
    for name, _, _ in reversed(SETTINGS_COLUMNS):
        op.drop_column("settings", name)

    op.drop_column("media_files", "quick_hash")
    op.drop_column("media", "pixel_hash")
    op.drop_column("media", "quick_hash")

    op.add_column(
        "albums", sa.Column("folder_modified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_column("albums", "last_sync_message")
    op.drop_column("albums", "last_sync_status")
    op.drop_column("albums", "last_sync_at")
    op.drop_column("albums", "entry_signature")

    for enum in (CHANGE_KIND, SYNC_TRIGGER):
        enum.drop(op.get_bind(), checkfirst=False)
